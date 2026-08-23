"""Frozen T5.4 headline analysis over the completed Phase-5 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cobol_archaeologist.eval.calibration import calibration
from cobol_archaeologist.eval.live import ROOT
from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.eval.metrics import (
    DRIFT_TYPES,
    classification,
    detection,
    evaluate,
)
from cobol_archaeologist.eval.phase5 import BinaryBaselineRecord, binary_detection
from cobol_archaeologist.eval.phase5_reuse import confirm_m4_reranker_identity
from cobol_archaeologist.eval.schemas import EvaluationRecord, TrajectoryAssessment
from cobol_archaeologist.eval.statistics import (
    paired_bootstrap_delta,
    paired_randomization_p,
)
from cobol_archaeologist.eval.trajectory import assess_all
from cobol_archaeologist.schemas import DriftInstance

CANONICAL_TEST_SHA256 = (
    "bc9e775a727d82c7d5a30fd0495512bffde173bec2580e3d08664b8d98b2aed4"
)
CANONICAL_TRAIN_SHA256 = (
    "75ff2f797328fa7672365e1337e1483c37010e886cc1bafc2aba3ca045943904"
)
CANONICAL_PROBE_SHA256 = (
    "f1ca51910fc8d7d76e1a469884ff51d1de87f1efc2850d5d7ab54558930e128b"
)
EXCLUDED_IDS = frozenset(
    {
        "drift_000001",
        "drift_000003",
        "drift_110001",
        "drift_110003",
        "drift_110005",
        "drift_110007",
        "drift_110009",
        "drift_110023",
    }
)
CI_FRAGILE_THRESHOLD = 10
PRIMARY_SEED = 20260823

M5 = ROOT / "data" / "eval" / "m5"
FROZEN_TEST = ROOT / "data" / "benchmark" / "v1" / "test.jsonl"
BENCHMARK_MANIFEST = ROOT / "data" / "benchmark" / "v1" / "manifest.json"
ANNOTATION_PATHS = {
    "pass_a": ROOT / "data" / "benchmark" / "annotation" / "pass_1_Human-Primary.jsonl",
    "pass_b": ROOT
    / "data"
    / "benchmark"
    / "annotation"
    / "pass_2_Claude-Verification.jsonl",
    "adjudications": ROOT
    / "data"
    / "benchmark"
    / "annotation"
    / "adjudication_log.jsonl",
    "adjudicated_real": ROOT
    / "data"
    / "benchmark"
    / "annotation"
    / "real_curated_resolved_v1.jsonl",
}
STRUCTURED_PATHS = {
    "agent": (
        M5 / "agent-rerun" / "agent.jsonl",
        M5 / "agent-rerun" / "agent.manifest.json",
    ),
    "plain_llm": (
        M5 / "plain_llm" / "plain_llm.jsonl",
        M5 / "plain_llm" / "plain_llm.manifest.json",
    ),
    "rag_dense": (
        M5 / "rag_dense" / "rag_dense.jsonl",
        M5 / "rag_dense" / "rag_dense.manifest.json",
    ),
    "rag_reranker": (
        M5 / "rag_reranker" / "rag_reranker.jsonl",
        M5 / "rag_reranker" / "rag_reranker.manifest.json",
    ),
    "oracle_slice": (
        M5 / "oracle_slice-rerun" / "oracle_slice.jsonl",
        M5 / "oracle_slice-rerun" / "oracle_slice.manifest.json",
    ),
}
BINARY_SYSTEMS = (
    "train_majority",
    "prevalence_random",
    "static_keyword",
    "attacker_with_bases",
)
BINARY_PATHS = {
    name: (
        M5 / "baselines" / f"{name}.jsonl",
        M5 / "baselines" / f"{name}.manifest.json",
    )
    for name in BINARY_SYSTEMS
}
PROJECTION_SOURCE_MANIFESTS = (
    ROOT / "data" / "eval" / "m4" / "agent.manifest.json",
    ROOT / "data" / "eval" / "m4" / "dense_rag.manifest.json",
    ROOT / "data" / "eval" / "m4" / "oracle_slice.manifest.json",
    M5 / "agent-rerun" / "full" / "agent.manifest.json",
    M5 / "rag_reranker-rerun" / "full" / "rag_reranker.manifest.json",
    M5 / "oracle_slice-rerun" / "full" / "oracle_slice.manifest.json",
)
FROZEN_INPUT_PATHS = tuple(
    [FROZEN_TEST, BENCHMARK_MANIFEST, *ANNOTATION_PATHS.values()]
    + [path for pair in STRUCTURED_PATHS.values() for path in pair]
    + [path for pair in BINARY_PATHS.values() for path in pair]
    + list(PROJECTION_SOURCE_MANIFESTS)
)
REQUIRED_ERROR_CATEGORIES = frozenset(
    {
        "false_positives",
        "false_negatives",
        "abstentions",
        "wrong_drift_class",
        "localization_failures",
        "evidence_verification_failures",
        "interprocedural_failures",
        "wrong_version_or_clause",
    }
)


@dataclass(frozen=True)
class FrozenInputs:
    gold: list[DriftInstance]
    structured: dict[str, list[EvaluationRecord]]
    binary: dict[str, list[BinaryBaselineRecord]]
    manifests: dict[str, dict[str, Any]]
    identities: dict[str, dict[str, Any]]
    benchmark: dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _crlf_sha256(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(normalized).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path, model: Any) -> list[Any]:
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_provider_identity(manifest: dict[str, Any], system_id: str) -> None:
    _require(
        manifest["system_id"] == system_id, f"{system_id} manifest system mismatch"
    )
    _require(manifest["model_id"] == "gpt-5.6-luna", f"{system_id} model mismatch")
    _require(manifest["schema_version"] == "3", f"{system_id} schema mismatch")
    _require(
        manifest["split_sha256"] == CANONICAL_TEST_SHA256,
        f"{system_id} split identity mismatch",
    )
    _require(
        manifest["prompt_version"] == "m4-live-codex-batch-v4",
        f"{system_id} prompt mismatch",
    )
    _require(
        manifest["decoding"]["reasoning_effort"] == "low",
        f"{system_id} reasoning-effort mismatch",
    )
    expected_budget = (
        {
            "max_steps": 8,
            "max_tool_calls": 8,
            "max_tokens": 65536,
            "wall_clock_timeout_s": 600.0,
            "max_contract_repairs": 1,
        }
        if system_id == "agent"
        else {
            "max_steps": 1,
            "max_tool_calls": 0,
            "max_tokens": 16384,
            "wall_clock_timeout_s": 180.0,
            "max_contract_repairs": 1,
        }
    )
    _require(
        manifest["budgets"] == expected_budget,
        f"{system_id} budget or tool-access identity mismatch",
    )


def _validate_projection(
    system_id: str,
    manifest: dict[str, Any],
    records: Sequence[EvaluationRecord],
) -> dict[str, Any]:
    _require(
        manifest.get("artifact_kind") == "t5.3_reuse_projection_v1",
        f"{system_id} is not the frozen T5.3 projection",
    )
    _require(
        manifest["validity"]["status"] == "VALID", f"{system_id} projection is invalid"
    )
    _require(
        manifest["validity"]["infrastructure_failures"] == 0,
        f"{system_id} has infrastructure failures",
    )
    _require(
        manifest["validity"]["contract_rejections"] == 0,
        f"{system_id} has contract rejections",
    )
    _require(
        manifest["completed_run_keys"] == [row.run_key for row in records],
        f"{system_id} projection run keys do not align",
    )
    sources: dict[str, Any] = {}
    for kind in ("reuse", "rerun"):
        entry = manifest[kind]
        manifest_path = (
            ROOT / entry["historical_manifest" if kind == "reuse" else "manifest"]
        )
        expected_hash = entry[
            "historical_manifest_sha256" if kind == "reuse" else "manifest_sha256"
        ]
        _require(
            _sha256(manifest_path) == expected_hash,
            f"{system_id} {kind} manifest hash mismatch",
        )
        sources[kind] = {
            "manifest": _relative(manifest_path),
            "manifest_sha256": expected_hash,
            "identity": _json(manifest_path),
        }
    historical = sources["reuse"]["identity"]
    _require(
        historical["model_id"] == "gpt-5.6-luna",
        f"{system_id} historical model mismatch",
    )
    _require(
        historical["decoding"]["reasoning_effort"] == "high",
        f"{system_id} historical effort mismatch",
    )
    _require(
        historical["prompt_version"] == "m4-live-codex-batch-v3",
        f"{system_id} historical prompt mismatch",
    )
    _require(
        historical["schema_version"] == "3", f"{system_id} historical schema mismatch"
    )
    rerun = sources["rerun"]["identity"]
    _validate_provider_identity(rerun, system_id)
    if system_id == "rag_reranker":
        proof = confirm_m4_reranker_identity()
        _require(
            manifest.get("search_identity") == proof,
            "rag_reranker immutable search identity proof mismatch",
        )
    return {
        "projection_kind": manifest["artifact_kind"],
        "historical_model": historical["model_id"],
        "historical_reasoning_effort": historical["decoding"]["reasoning_effort"],
        "historical_prompt_version": historical["prompt_version"],
        "rerun_model": rerun["model_id"],
        "rerun_reasoning_effort": rerun["decoding"]["reasoning_effort"],
        "rerun_prompt_version": rerun["prompt_version"],
        "reused_rows": manifest["reuse"]["reused_rows"],
        "rerun_rows": manifest["rerun"]["rows"],
        "mixed_provenance_disclosure": (
            "Descriptive paired system comparison; not a controlled prompt or reasoning-effort ablation."
        ),
    }


def load_frozen_inputs() -> FrozenInputs:
    """Load and fail closed on every frozen T5.4 input identity."""

    benchmark_manifest = _json(BENCHMARK_MANIFEST)
    _require(
        _sha256(FROZEN_TEST) == CANONICAL_TEST_SHA256, "canonical LF test hash mismatch"
    )
    _require(
        set(benchmark_manifest["excluded_candidate_ids"]) == EXCLUDED_IDS,
        "excluded-candidate identity mismatch",
    )
    for name, path in ANNOTATION_PATHS.items():
        _require(
            _crlf_sha256(path)
            == benchmark_manifest["annotation_evidence_sha256"][name],
            f"annotation evidence hash mismatch: {name}",
        )

    gold = _jsonl(FROZEN_TEST, DriftInstance)
    frozen_ids = [row.instance_id for row in gold]
    _require(len(gold) == 196, f"expected 196 frozen rows, found {len(gold)}")
    _require(len(set(frozen_ids)) == 196, "frozen benchmark contains duplicate IDs")
    _require(
        not (set(frozen_ids) & EXCLUDED_IDS), "excluded IDs appear in frozen benchmark"
    )
    gold_by_id = {row.instance_id: row for row in gold}

    structured: dict[str, list[EvaluationRecord]] = {}
    binary: dict[str, list[BinaryBaselineRecord]] = {}
    manifests: dict[str, dict[str, Any]] = {}
    identities: dict[str, dict[str, Any]] = {}
    expected_offline = {
        "train_majority": "m5-train-majority-v1",
        "prevalence_random": "m5-random-v1",
        "static_keyword": "m5-static-keyword-v1",
        "attacker_with_bases": "m5-attacker-with-bases-v1",
    }

    for system_id, (records_path, manifest_path) in STRUCTURED_PATHS.items():
        records = _jsonl(records_path, EvaluationRecord)
        manifest = _json(manifest_path)
        ids = [row.instance_id for row in records]
        _require(
            ids == frozen_ids, f"{system_id} instance IDs do not match frozen order"
        )
        _require(len(set(ids)) == 196, f"{system_id} contains duplicate IDs")
        _require(
            all(row.system_id == system_id for row in records),
            f"{system_id} record identity mismatch",
        )
        _require(
            all(row.gold == gold_by_id[row.instance_id] for row in records),
            f"{system_id} gold binding mismatch",
        )
        _require(
            all(
                row.source_sha256 == materialize(row.gold).source_sha256
                for row in records
            ),
            f"{system_id} source identity mismatch",
        )
        _require(
            not any(row.infrastructure_error for row in records),
            f"{system_id} infrastructure failure",
        )
        _require(
            all(
                row.abstained or bool(row.verification and row.verification.verified)
                for row in records
            ),
            f"{system_id} contains an unverified emission",
        )
        _require(
            manifest["system_id"] == system_id, f"{system_id} manifest system mismatch"
        )
        _require(manifest["total"] == 196, f"{system_id} manifest row-count mismatch")
        _require(
            manifest["split_sha256"] == CANONICAL_TEST_SHA256,
            f"{system_id} manifest split mismatch",
        )
        if system_id in {"plain_llm", "rag_dense"}:
            _validate_provider_identity(manifest, system_id)
            _require(
                manifest["validity"]["status"] == "VALID", f"{system_id} run is invalid"
            )
            _require(
                manifest["validity"]["infrastructure_failures"] == 0,
                f"{system_id} infrastructure failures",
            )
            _require(
                manifest["validity"]["contract_rejections"] == 0,
                f"{system_id} contract rejections",
            )
            _require(
                len(manifest["completed_run_keys"]) == 196
                and set(manifest["completed_run_keys"])
                == {row.run_key for row in records},
                f"{system_id} run-key mismatch",
            )
            provider_identity: dict[str, Any] = {
                "model": manifest["model_id"],
                "reasoning_effort": manifest["decoding"]["reasoning_effort"],
                "prompt_version": manifest["prompt_version"],
                "schema_version": manifest["schema_version"],
                "retrieval_mode": "none" if system_id == "plain_llm" else "dense",
            }
        else:
            provider_identity = _validate_projection(system_id, manifest, records)
        identities[system_id] = {
            "system_id": system_id,
            "artifact": _relative(records_path),
            "artifact_sha256": _sha256(records_path),
            "manifest": _relative(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "row_count": len(records),
            "unique_instance_ids": len(set(ids)),
            "instance_ids_match_frozen_order": ids == frozen_ids,
            "source_identity_matches": True,
            "gold_identity_matches": True,
            "infrastructure_failures": 0,
            "unverified_emissions": 0,
            "provider_identity": provider_identity,
            "provenance_status": (
                "reuse/rerun projection provenance recorded"
                if system_id not in {"plain_llm", "rag_dense"}
                else "new homogeneous frozen T5.3 provider run"
            ),
            "reuse_rerun_provenance_present": (
                True
                if system_id not in {"plain_llm", "rag_dense"}
                else "not_applicable"
            ),
        }
        structured[system_id] = records
        manifests[system_id] = manifest

    for system_id, (records_path, manifest_path) in BINARY_PATHS.items():
        records = _jsonl(records_path, BinaryBaselineRecord)
        manifest = _json(manifest_path)
        ids = [row.instance_id for row in records]
        _require(
            ids == frozen_ids, f"{system_id} instance IDs do not match frozen order"
        )
        _require(len(set(ids)) == 196, f"{system_id} contains duplicate IDs")
        _require(
            all(row.system_id == system_id for row in records),
            f"{system_id} record identity mismatch",
        )
        _require(
            all(
                row.gold_is_drift
                == (gold_by_id[row.instance_id].drift_type != "D7_conformant")
                for row in records
            ),
            f"{system_id} gold verdict mismatch",
        )
        _require(
            all(
                row.source_sha256
                == materialize(gold_by_id[row.instance_id]).source_sha256
                for row in records
            ),
            f"{system_id} source identity mismatch",
        )
        _require(manifest["system_id"] == system_id, f"{system_id} manifest mismatch")
        _require(manifest["total"] == 196, f"{system_id} manifest row-count mismatch")
        _require(
            manifest["split_sha256"] == CANONICAL_TEST_SHA256,
            f"{system_id} manifest split mismatch",
        )
        _require(
            manifest["implementation_identity"] == expected_offline[system_id],
            f"{system_id} implementation identity mismatch",
        )
        if system_id == "attacker_with_bases":
            _require(
                manifest["source_probe_sha256"] == CANONICAL_PROBE_SHA256,
                "attacker probe hash mismatch",
            )
            _require(
                all(weight == 0.0 for weight in manifest["parameters"]["weights"]),
                "attacker weights changed",
            )
        identities[system_id] = {
            "system_id": system_id,
            "artifact": _relative(records_path),
            "artifact_sha256": _sha256(records_path),
            "manifest": _relative(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "row_count": len(records),
            "unique_instance_ids": len(set(ids)),
            "instance_ids_match_frozen_order": ids == frozen_ids,
            "source_identity_matches": True,
            "gold_identity_matches": True,
            "infrastructure_failures": 0,
            "unverified_emissions": 0,
            "implementation_identity": manifest["implementation_identity"],
            "provenance_status": "deterministic frozen T5.3 baseline build",
            "reuse_rerun_provenance_present": "not_applicable",
        }
        binary[system_id] = records
        manifests[system_id] = manifest

    id_hash = hashlib.sha256("\n".join(frozen_ids).encode()).hexdigest()
    benchmark = {
        "path": _relative(FROZEN_TEST),
        "sha256": _sha256(FROZEN_TEST),
        "canonical_lf_sha256": CANONICAL_TEST_SHA256,
        "canonical_lf_identity_used": True,
        "stale_manifest_crlf_hash_ignored": benchmark_manifest["split_sha256"]["test"],
        "row_count": len(gold),
        "unique_instance_ids": len(set(frozen_ids)),
        "instance_ids_sha256": id_hash,
        "local_rows": sum(not row.code_locus.is_interprocedural for row in gold),
        "interprocedural_rows": sum(row.code_locus.is_interprocedural for row in gold),
        "real_curated_rows": sum(
            row.provenance.source == "real_curated" for row in gold
        ),
        "excluded_candidate_ids": sorted(EXCLUDED_IDS),
        "excluded_ids_present": sorted(set(frozen_ids) & EXCLUDED_IDS),
        "annotation_evidence": {
            name: {
                "path": _relative(path),
                "canonical_lf_sha256": _sha256(path),
                "manifest_crlf_sha256": _crlf_sha256(path),
                "manifest_crlf_identity_matches": (
                    _crlf_sha256(path)
                    == benchmark_manifest["annotation_evidence_sha256"][name]
                ),
            }
            for name, path in ANNOTATION_PATHS.items()
        },
    }
    return FrozenInputs(gold, structured, binary, manifests, identities, benchmark)


def _balanced_accuracy_structured(records: Sequence[EvaluationRecord]) -> float:
    positives = [row for row in records if row.gold.drift_type != "D7_conformant"]
    negatives = [row for row in records if row.gold.drift_type == "D7_conformant"]
    true_positive = sum(
        not row.infrastructure_error
        and not row.abstained
        and row.prediction is not None
        and row.prediction.drift_type != "D7_conformant"
        for row in positives
    )
    true_negative = sum(
        not row.infrastructure_error
        and not row.abstained
        and row.prediction is not None
        and row.prediction.drift_type == "D7_conformant"
        for row in negatives
    )
    sensitivity = true_positive / len(positives) if positives else 0.0
    specificity = true_negative / len(negatives) if negatives else 0.0
    return (sensitivity + specificity) / 2


def _balanced_accuracy_binary(records: Sequence[BinaryBaselineRecord]) -> float:
    positives = [row for row in records if row.gold_is_drift]
    negatives = [row for row in records if not row.gold_is_drift]
    sensitivity = (
        sum(row.predicted_is_drift for row in positives) / len(positives)
        if positives
        else 0.0
    )
    specificity = (
        sum(not row.predicted_is_drift for row in negatives) / len(negatives)
        if negatives
        else 0.0
    )
    return (sensitivity + specificity) / 2


def _structured_t1(records: Sequence[EvaluationRecord]) -> dict[str, Any]:
    result = detection(records)
    result.update(
        {
            "balanced_accuracy": _balanced_accuracy_structured(records),
            "support": len(records),
            "answered": sum(
                not row.infrastructure_error and not row.abstained for row in records
            ),
            "abstained": sum(
                not row.infrastructure_error and row.abstained for row in records
            ),
        }
    )
    return result


def _binary_t1(records: Sequence[BinaryBaselineRecord]) -> dict[str, Any]:
    result = binary_detection(list(records))
    result.update(
        {
            "balanced_accuracy": _balanced_accuracy_binary(records),
            "support": len(records),
            "answered": len(records),
            "abstained": 0,
            "answered_accuracy": sum(
                row.gold_is_drift == row.predicted_is_drift for row in records
            )
            / len(records),
        }
    )
    return result


def _confusion_matrix(records: Sequence[EvaluationRecord]) -> dict[str, dict[str, int]]:
    columns = (*DRIFT_TYPES, "ABSTAIN")
    matrix = {gold: {predicted: 0 for predicted in columns} for gold in DRIFT_TYPES}
    for row in records:
        predicted = (
            "ABSTAIN"
            if row.abstained or row.prediction is None
            else row.prediction.drift_type
        )
        matrix[row.gold.drift_type][predicted] += 1
    return matrix


def _fragility(support: int) -> str:
    return "CI-fragile" if support < CI_FRAGILE_THRESHOLD else "ok"


def _metrics(
    frozen: FrozenInputs,
    assessments: Sequence[TrajectoryAssessment],
) -> tuple[dict[str, Any], list[str]]:
    gold_by_id = {row.instance_id: row for row in frozen.gold}
    metrics: dict[str, Any] = {}
    fragile_cells: set[str] = set()
    for system_id in (*STRUCTURED_PATHS, *BINARY_PATHS):
        is_structured = system_id in frozen.structured
        records: Sequence[Any] = (
            frozen.structured[system_id] if is_structured else frozen.binary[system_id]
        )
        local = [
            row
            for row in records
            if not gold_by_id[row.instance_id].code_locus.is_interprocedural
        ]
        interprocedural = [
            row
            for row in records
            if gold_by_id[row.instance_id].code_locus.is_interprocedural
        ]
        scorer = _structured_t1 if is_structured else _binary_t1
        class_metrics: dict[str, Any] = {}
        classification_result = classification(records) if is_structured else None
        for drift_type in DRIFT_TYPES:
            rows = [
                row
                for row in records
                if gold_by_id[row.instance_id].drift_type == drift_type
            ]
            local_rows = [
                row
                for row in rows
                if not gold_by_id[row.instance_id].code_locus.is_interprocedural
            ]
            inter_rows = [
                row
                for row in rows
                if gold_by_id[row.instance_id].code_locus.is_interprocedural
            ]
            statuses = {
                "overall": _fragility(len(rows)),
                "local": _fragility(len(local_rows)),
                "interprocedural": _fragility(len(inter_rows)),
            }
            for locus, status in statuses.items():
                if status == "CI-fragile":
                    fragile_cells.add(f"{drift_type}/{locus}")
            class_metrics[drift_type] = {
                "support": len(rows),
                "local_support": len(local_rows),
                "interprocedural_support": len(inter_rows),
                "answer_rate": scorer(rows)["answer_rate"],
                "t1_within_gold_class": scorer(rows),
                "t3_one_vs_rest": (
                    classification_result["per_class"][drift_type]
                    if classification_result
                    else {
                        "precision": "not_applicable",
                        "recall": "not_applicable",
                        "f1": "not_applicable",
                        "reason": "binary-only baseline emits no D1-D7 class",
                    }
                ),
                "fragility": statuses,
            }
        result: dict[str, Any] = {
            "overall": scorer(records),
            "locus": {
                "local": scorer(local),
                "interprocedural": scorer(interprocedural),
            },
            "class_strata": class_metrics,
        }
        if is_structured:
            evaluated = evaluate(records, assessments if system_id == "agent" else ())
            result["t2_localization"] = evaluated["overall"]["t2_localization"]
            result["t3_classification"] = {
                **evaluated["overall"]["t3_classification"],
                "confusion_matrix": _confusion_matrix(records),
            }
        else:
            result["t2_localization"] = "not_applicable"
            result["t3_classification"] = "not_applicable"
        metrics[system_id] = result
    return metrics, sorted(fragile_cells)


def _correct_binary(record: EvaluationRecord) -> bool:
    return bool(
        not record.infrastructure_error
        and not record.abstained
        and record.prediction is not None
        and (record.prediction.drift_type != "D7_conformant")
        == (record.gold.drift_type != "D7_conformant")
    )


def paired_f1_comparison(
    left: Sequence[EvaluationRecord],
    right: Sequence[EvaluationRecord],
    *,
    locus: Literal["overall", "local", "interprocedural"],
    bootstrap_resamples: int,
    randomization_samples: int,
    seed: int,
) -> dict[str, Any]:
    """Compute a paired F1 comparison, refusing partial or duplicate pairing."""

    left_ids = [row.instance_id for row in left]
    right_ids = [row.instance_id for row in right]
    if len(left_ids) != len(set(left_ids)) or len(right_ids) != len(set(right_ids)):
        raise ValueError("paired comparison contains duplicate instance IDs")
    if set(left_ids) != set(right_ids):
        raise ValueError("paired comparison instance IDs do not align")
    right_by_id = {row.instance_id: row for row in right}
    paired_left: list[EvaluationRecord] = []
    paired_right: list[EvaluationRecord] = []
    for row in left:
        include = locus == "overall" or row.gold.code_locus.is_interprocedural == (
            locus == "interprocedural"
        )
        if include:
            paired_left.append(row)
            paired_right.append(right_by_id[row.instance_id])
    if not paired_left:
        raise ValueError("paired comparison stratum is empty")

    def metric(rows: Sequence[object]) -> float:
        return detection(rows)["f1"]  # type: ignore[arg-type]

    delta, low, high = paired_bootstrap_delta(
        paired_left,
        paired_right,
        metric,
        resamples=bootstrap_resamples,
        seed=seed,
    )
    p_value = paired_randomization_p(
        [_correct_binary(row) for row in paired_left],
        [_correct_binary(row) for row in paired_right],
        samples=randomization_samples,
        seed=seed,
    )
    direction = "positive" if delta > 0 else "negative" if delta < 0 else "zero"
    return {
        "left_system": paired_left[0].system_id,
        "right_system": paired_right[0].system_id,
        "locus": locus,
        "paired_rows": len(paired_left),
        "left_f1": detection(paired_left)["f1"],
        "right_f1": detection(paired_right)["f1"],
        "delta_f1": delta,
        "bootstrap_95_ci": [low, high],
        "paired_randomization_p": p_value,
        "effect_size": {
            "metric": "absolute_f1_difference",
            "magnitude": abs(delta),
            "direction": direction,
        },
    }


def _risk_coverage(records: Sequence[EvaluationRecord]) -> list[dict[str, float | int]]:
    answered = sorted(
        [row for row in records if not row.abstained and row.prediction is not None],
        key=lambda row: (-float(row.confidence), row.instance_id),
    )
    points = []
    for fraction in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        count = min(len(answered), max(1, math.ceil(len(answered) * fraction)))
        selected = answered[:count]
        accuracy = (
            sum(row.prediction.drift_type == row.gold.drift_type for row in selected)
            / count
        )
        point = {
            "selected_rows": count,
            "full_set_coverage": count / len(records),
            "answered_subset_fraction": count / len(answered),
            "selective_accuracy": accuracy,
            "selective_risk": 1 - accuracy,
        }
        if not points or point != points[-1]:
            points.append(point)
    return points


def _agent_evidence(
    records: Sequence[EvaluationRecord],
    assessments: Sequence[TrajectoryAssessment],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evaluated = evaluate(records, assessments)
    calibration_result = calibration(records, assessments)
    assessment_by_id = {row.instance_id: row for row in assessments}
    answered = [row for row in records if not row.abstained]
    clause_correct = sum(
        row.prediction.regulation_clause == row.gold.regulation_clause
        for row in answered
    )
    code_correct = sum(
        bool(assessment_by_id[row.instance_id].code_fact_ok) for row in answered
    )
    faithfulness = {
        **evaluated["overall"]["t4_faithfulness"],
        "clause_evidence_accuracy": clause_correct / len(answered)
        if answered
        else None,
        "code_evidence_accuracy": code_correct / len(answered) if answered else None,
        "answered_rows": len(answered),
    }
    calibration_result["risk_coverage"] = _risk_coverage(records)
    abstained = [row for row in records if row.abstained]
    abstention = {
        "total_answered": len(answered),
        "total_abstained": len(abstained),
        "answer_rate": len(answered) / len(records),
        "abstention_rate": len(abstained) / len(records),
        "by_drift_class": dict(
            sorted(Counter(row.gold.drift_type for row in abstained).items())
        ),
        "by_locus": {
            "local": sum(
                not row.gold.code_locus.is_interprocedural for row in abstained
            ),
            "interprocedural": sum(
                row.gold.code_locus.is_interprocedural for row in abstained
            ),
        },
        "interpretation": (
            "Abstentions remain full-coverage misses where applicable; answered-subset accuracy is not the headline."
        ),
    }
    return faithfulness, calibration_result, abstention


def _trajectory_resources(
    records: Sequence[EvaluationRecord], *, agent: bool
) -> dict[str, Any]:
    trajectories = []
    if agent:
        trajectories = [
            trace.trajectory for row in records for trace in row.agent_hunts
        ]
    else:
        trajectories = [row.trajectory for row in records if row.trajectory is not None]
    tool_calls = [step for trajectory in trajectories for step in trajectory.steps]
    latencies = [step.latency_ms for step in tool_calls if step.latency_ms is not None]
    return {
        "provider_turns_recomputed": sum(
            len(row.model_responses) for row in trajectories
        ),
        "token_count_total": sum(row.tokens_used for row in trajectories),
        "tool_calls": len(tool_calls),
        "successful_tool_observations": sum(step.error is None for step in tool_calls),
        "mean_successful_tool_observations_per_row": (
            sum(step.error is None for step in tool_calls) / len(records)
        ),
        "execution_tool_calls": sum(step.tool == "run_cobol" for step in tool_calls),
        "contract_repairs_recomputed": sum(
            row.contract_repairs for row in trajectories
        ),
        "tool_latency_ms_total": sum(latencies) if latencies else "not_recorded",
        "tool_latency_ms_mean": sum(latencies) / len(latencies)
        if latencies
        else "not_recorded",
        "provider_end_to_end_latency": "not_recorded",
        "monetary_cost": "not_recorded",
    }


def _cost_efficiency(frozen: FrozenInputs) -> dict[str, Any]:
    systems: dict[str, Any] = {}
    for system_id, records in frozen.structured.items():
        manifest = frozen.manifests[system_id]
        validity = manifest["validity"]
        resources = _trajectory_resources(records, agent=system_id == "agent")
        _require(
            resources["provider_turns_recomputed"] == validity["provider_turns"],
            f"{system_id} provider-turn accounting mismatch",
        )
        _require(
            resources["contract_repairs_recomputed"] == validity["contract_rejections"],
            f"{system_id} contract-repair accounting mismatch",
        )
        systems[system_id] = {
            "rows": len(records),
            "answer_rate": sum(not row.abstained for row in records) / len(records),
            "provider_turns": validity["provider_turns"],
            "contract_rejections": validity["contract_rejections"],
            **resources,
        }
    for system_id, records in frozen.binary.items():
        systems[system_id] = {
            "rows": len(records),
            "answer_rate": 1.0,
            "deterministic_predictions": len(records),
            "provider_turns": 0,
            "tool_calls": 0,
            "token_count_total": "not_recorded",
            "provider_end_to_end_latency": "not_recorded",
            "monetary_cost": "not_recorded",
        }
    return {
        "systems": systems,
        "dollar_cost": "not_recorded",
        "limitation": (
            "Runs used ChatGPT authentication rather than metered API billing; no token price or dollar cost is inferred."
        ),
    }


def _citation(record: EvaluationRecord) -> tuple[str, str, str, Any]:
    clause = record.prediction.regulation_clause
    return clause.doc, clause.clause_id, clause.version, clause.effective_date


def _gold_citation(record: EvaluationRecord) -> tuple[str, str, str, Any]:
    clause = record.gold.regulation_clause
    return clause.doc, clause.clause_id, clause.version, clause.effective_date


def _localization_failed(record: EvaluationRecord) -> bool:
    if record.abstained or record.prediction is None:
        return False
    if (
        record.gold.drift_type == "D7_conformant"
        or record.prediction.drift_type == "D7_conformant"
    ):
        return False
    gold_lines = {
        (row.program, row.file, row.line) for row in record.gold.labels.line_level
    }
    predicted_lines = {
        (row.program, row.file, row.line) for row in record.prediction.labels.line_level
    }
    if gold_lines:
        return not bool(gold_lines & predicted_lines)
    gold_programs = {row.program for row in record.gold.code_locus.loci}
    predicted_programs = {row.program for row in record.prediction.code_locus.loci}
    return not bool(gold_programs & predicted_programs)


def _failure_modes(records: Sequence[EvaluationRecord]) -> dict[str, int]:
    modes = Counter(
        {
            "retrieval_failure": 0,
            "reasoning_or_classification_failure": 0,
            "insufficient_evidence": 0,
            "verifier_rejection": 0,
            "slicing_or_context_failure": 0,
            "coverage_or_abstention_failure": 0,
            "root_cause_not_supported": 0,
        }
    )
    for row in records:
        reason = (row.abstention_reason or "").lower()
        if row.abstained:
            if "retriev" in reason or "search" in reason:
                modes["retrieval_failure"] += 1
            elif "slice" in reason or "context" in reason:
                modes["slicing_or_context_failure"] += 1
            elif "verif" in reason or "refut" in reason or "static-claim" in reason:
                modes["verifier_rejection"] += 1
            elif "evidence" in reason or "insufficient" in reason:
                modes["insufficient_evidence"] += 1
            else:
                modes["coverage_or_abstention_failure"] += 1
        elif row.prediction and row.prediction.drift_type != row.gold.drift_type:
            modes["reasoning_or_classification_failure"] += 1
        elif _localization_failed(row):
            modes["root_cause_not_supported"] += 1
    return dict(modes)


def _category(
    rows: Sequence[EvaluationRecord],
    *,
    applicable: int,
    description: str,
) -> dict[str, Any]:
    return {
        "count": len(rows),
        "applicable_rows": applicable,
        "share_of_applicable_errors": len(rows) / applicable if applicable else 0.0,
        "affected_drift_classes": dict(
            sorted(Counter(row.gold.drift_type for row in rows).items())
        ),
        "locus_distribution": {
            "local": sum(not row.gold.code_locus.is_interprocedural for row in rows),
            "interprocedural": sum(
                row.gold.code_locus.is_interprocedural for row in rows
            ),
        },
        "representative_instance_ids": sorted(row.instance_id for row in rows)[:5],
        "description": description,
    }


def _error_analysis(
    frozen: FrozenInputs,
    assessments: Sequence[TrajectoryAssessment],
) -> dict[str, Any]:
    assessment_by_id = {row.instance_id: row for row in assessments}
    systems: dict[str, Any] = {}
    for system_id, records in frozen.structured.items():
        false_positives = [
            row
            for row in records
            if row.gold.drift_type == "D7_conformant"
            and not row.abstained
            and row.prediction.drift_type != "D7_conformant"
        ]
        false_negatives = [
            row
            for row in records
            if row.gold.drift_type != "D7_conformant"
            and (row.abstained or row.prediction.drift_type == "D7_conformant")
        ]
        abstentions = [row for row in records if row.abstained]
        wrong_class = [
            row
            for row in records
            if not row.abstained and row.prediction.drift_type != row.gold.drift_type
        ]
        localization_failures = [row for row in records if _localization_failed(row)]
        evidence_failures = [
            row
            for row in records
            if (
                row.abstained
                and any(
                    token in (row.abstention_reason or "").lower()
                    for token in ("verif", "refut", "static-claim")
                )
            )
            or (
                system_id == "agent"
                and not row.abstained
                and not (
                    assessment_by_id[row.instance_id].evidence_path_ok
                    and assessment_by_id[row.instance_id].code_fact_ok
                )
            )
        ]
        interprocedural_failures = [
            row
            for row in records
            if row.gold.code_locus.is_interprocedural
            and (row.abstained or row.prediction.drift_type != row.gold.drift_type)
        ]
        wrong_citation = [
            row
            for row in records
            if not row.abstained and _citation(row) != _gold_citation(row)
        ]
        binary_errors = len(false_positives) + len(false_negatives)
        answered = sum(not row.abstained for row in records)
        interprocedural = sum(row.gold.code_locus.is_interprocedural for row in records)
        categories = {
            "false_positives": _category(
                false_positives,
                applicable=binary_errors,
                description="Answered conformant rows classified as drift.",
            ),
            "false_negatives": _category(
                false_negatives,
                applicable=binary_errors,
                description="Drift rows abstained on or answered conformant; abstentions remain full-coverage misses.",
            ),
            "abstentions": _category(
                abstentions,
                applicable=len(records),
                description="Rows with no emitted verified prediction.",
            ),
            "wrong_drift_class": _category(
                wrong_class,
                applicable=answered,
                description="Answered rows whose D1-D7 class differs from frozen gold.",
            ),
            "localization_failures": _category(
                localization_failures,
                applicable=answered,
                description="Answered drift findings with no overlap at the frozen typed line/program locus.",
            ),
            "evidence_verification_failures": _category(
                evidence_failures,
                applicable=len(records),
                description="Frozen trajectories support verifier rejection or incomplete grounded evidence; no tier is promoted.",
            ),
            "interprocedural_failures": _category(
                interprocedural_failures,
                applicable=interprocedural,
                description="Interprocedural rows abstained on or assigned the wrong D1-D7 class.",
            ),
            "wrong_version_or_clause": _category(
                wrong_citation,
                applicable=answered,
                description="Answered findings cite a clause document, identifier, version, or effective date different from gold.",
            ),
        }
        _require(
            set(categories) == REQUIRED_ERROR_CATEGORIES,
            "error categories are incomplete",
        )
        systems[system_id] = categories
        systems[system_id]["failure_mode_evidence"] = _failure_modes(records)
    summary = {
        system_id: {
            "binary_errors": categories["false_positives"]["count"]
            + categories["false_negatives"]["count"],
            "abstentions": categories["abstentions"]["count"],
            "wrong_class": categories["wrong_drift_class"]["count"],
            "interprocedural_failures": categories["interprocedural_failures"]["count"],
        }
        for system_id, categories in systems.items()
    }
    return {
        "status": "EVALUABLE",
        "method": (
            "Deterministic categorization from frozen gold, predictions, verification records, and trajectories. "
            "Categories may overlap; each share names its own applicable denominator."
        ),
        "root_cause_rule": "No root cause is assigned unless a frozen abstention reason or trajectory supports it.",
        "systems": systems,
        "summary": summary,
    }


def _not_evaluable(issue: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "status": "NOT_EVALUABLE",
            "issues": [issue],
            "benchmark": {},
            "system_identities": {},
            "metrics": {},
            "paired_comparisons": {},
            "faithfulness": {},
            "calibration": {},
            "abstention": {},
            "t6": {},
            "cost_efficiency": {},
            "error_analysis_summary": {},
            "frozen_decisions": {},
            "amendments": [],
            "headline_result": {},
        },
        {"status": "NOT_EVALUABLE", "issues": [issue], "systems": {}, "summary": {}},
    )


def build_headline_outputs(
    *,
    bootstrap_resamples: int = 10_000,
    randomization_samples: int = 20_000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the T5.4 report and error analysis without mutating frozen inputs."""

    if bootstrap_resamples < 1 or randomization_samples < 1:
        return _not_evaluable("statistical sample counts must be positive")
    try:
        frozen = load_frozen_inputs()
        agent = frozen.structured["agent"]
        assessments = assess_all(agent)
        metrics, fragile_cells = _metrics(frozen, assessments)
        comparisons: dict[str, Any] = {}
        primary = paired_f1_comparison(
            agent,
            frozen.structured["rag_reranker"],
            locus="interprocedural",
            bootstrap_resamples=bootstrap_resamples,
            randomization_samples=randomization_samples,
            seed=PRIMARY_SEED,
        )
        comparisons["primary"] = primary
        comparisons["secondary"] = {}
        for offset, comparator in enumerate(
            ("rag_dense", "plain_llm", "oracle_slice"), 1
        ):
            comparisons["secondary"][comparator] = {
                locus: paired_f1_comparison(
                    agent,
                    frozen.structured[comparator],
                    locus=locus,
                    bootstrap_resamples=bootstrap_resamples,
                    randomization_samples=randomization_samples,
                    seed=PRIMARY_SEED + offset * 10 + locus_offset,
                )
                for locus_offset, locus in enumerate(("overall", "interprocedural"))
            }
        comparisons["diagnostic_non_gating"] = {
            "attacker_note": (
                "Retained as null anti-gaming evidence only; the T5.3 surface floor is vacated."
            ),
            "agent_minus_attacker_overall_f1": metrics["agent"]["overall"]["f1"]
            - metrics["attacker_with_bases"]["overall"]["f1"],
        }
        faithfulness, calibration_result, abstention = _agent_evidence(
            agent, assessments
        )
        t6 = evaluate(agent, assessments)["overall"]["t6_versioned_judgment"]
        t6 = {
            **t6,
            "failures": t6["pairs"] - t6["successes"],
            "reporting_bar_status": "NOT_EVALUABLE_FOR_BAR",
            "minimum_pairs_required": 20,
            "interpretation": "Directional evidence only; nine pairs cannot satisfy the frozen 20-pair bar.",
        }
        _require(t6["pairs"] == 9, f"expected 9 T6 pairs, found {t6['pairs']}")
        error_analysis = _error_analysis(frozen, assessments)
        cost = _cost_efficiency(frozen)
        dense_bar = comparisons["secondary"]["rag_dense"]["interprocedural"]
        overall_bar = metrics["agent"]["overall"]["f1"] >= 0.70
        dense_bar_met = (
            dense_bar["delta_f1"] >= 0.10
            and dense_bar["bootstrap_95_ci"][0] > 0
            and dense_bar["paired_randomization_p"] < 0.05
        )
        direction_text = (
            "agent outperformed"
            if primary["delta_f1"] > 0
            else "agent underperformed"
            if primary["delta_f1"] < 0
            else "agent tied"
        )
        report = {
            "status": "EVALUABLE",
            "issues": [],
            "methodology": {
                "execution_type": "deterministic analysis over frozen T5.2/T5.3 artifacts",
                "provider_runs_performed": 0,
                "bootstrap_resamples": bootstrap_resamples,
                "randomization_samples": randomization_samples,
                "deterministic_seed": PRIMARY_SEED,
                "ci_fragile_support_threshold": CI_FRAGILE_THRESHOLD,
                "primary_comparison": "agent - rag_reranker, interprocedural full-coverage T1 F1",
                "paired_significance": "M4-compatible paired randomization over per-instance binary correctness",
            },
            "benchmark": frozen.benchmark,
            "system_identities": frozen.identities,
            "artifact_hashes": {
                name: {
                    "predictions": row["artifact_sha256"],
                    "manifest": row["manifest_sha256"],
                }
                for name, row in frozen.identities.items()
            },
            "metrics": metrics,
            "ci_fragile_cells": fragile_cells,
            "paired_comparisons": comparisons,
            "faithfulness": faithfulness,
            "calibration": calibration_result,
            "abstention": abstention,
            "t6": t6,
            "cost_efficiency": cost,
            "error_analysis_summary": error_analysis["summary"],
            "frozen_decisions": {
                "surface_floor": {
                    "status": "VACATED",
                    "used_as_pass_fail_gate": False,
                    "attacker_role": "null anti-gaming evidence",
                    "reason": "All six registered attacker weights and bias are zero; its score is a prevalence result.",
                },
                "contract_bars": {
                    "agent_overall_t1_f1_at_least_0_70": {
                        "observed": metrics["agent"]["overall"]["f1"],
                        "met": overall_bar,
                    },
                    "agent_over_dense_interprocedural_plus_0_10_ci_positive_p_lt_0_05": {
                        "observed": dense_bar,
                        "met": dense_bar_met,
                    },
                },
                "report_status_is_not_go_no_go": True,
            },
            "amendments": [
                "T5.3 Finding A option (c): attacker surface floor VACATED.",
                "T5.3 cross-platform identity: canonical LF test hash supersedes stale CRLF manifest hash.",
                "T5.3 Amendment 2: M4 projections carry mixed high/v3 reuse and low/v4 rerun provenance and are descriptive, not controlled ablations.",
            ],
            "headline_result": {
                "system": "agent",
                "comparator": "rag_reranker",
                "locus": "interprocedural",
                "metric": "full-coverage T1 F1",
                "agent_f1": primary["left_f1"],
                "comparator_f1": primary["right_f1"],
                "delta_f1": primary["delta_f1"],
                "bootstrap_95_ci": primary["bootstrap_95_ci"],
                "paired_randomization_p": primary["paired_randomization_p"],
                "direction": primary["effect_size"]["direction"],
                "statement": (
                    f"On the frozen 36-row interprocedural stratum, {direction_text} "
                    "the strongest frozen non-agentic model baseline."
                ),
            },
        }
        return report, error_analysis
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return _not_evaluable(str(exc))


def _fmt(value: Any) -> str:
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# T5.4 Frozen Phase-5 Headline Experiment — {report['status']}", ""]
    if report["status"] != "EVALUABLE":
        lines.extend(
            [
                "## Blocking issues",
                "",
                *[f"- {issue}" for issue in report["issues"]],
                "",
            ]
        )
        return "\n".join(lines)
    headline = report["headline_result"]
    lines.extend(
        [
            "## Headline result",
            "",
            headline["statement"],
            "",
            (
                f"Agent F1 {_fmt(headline['agent_f1'])} versus RAG+reranker "
                f"{_fmt(headline['comparator_f1'])}; ΔF1 {_fmt(headline['delta_f1'])}, "
                f"95% paired bootstrap CI [{_fmt(headline['bootstrap_95_ci'][0])}, "
                f"{_fmt(headline['bootstrap_95_ci'][1])}], paired randomization "
                f"p={_fmt(headline['paired_randomization_p'])} (n=36)."
            ),
            "",
            "This is the measured frozen result. No provider run or post-result configuration change occurred.",
            "",
            "## Artifact validity",
            "",
            "| System | Rows | Artifact SHA-256 | Infrastructure failures |",
            "|---|---:|---|---:|",
        ]
    )
    for name, identity in report["system_identities"].items():
        lines.append(
            f"| {name} | {identity['row_count']} | `{identity['artifact_sha256']}` | "
            f"{identity['infrastructure_failures']} |"
        )
    lines.extend(
        [
            "",
            (
                "The benchmark uses the canonical LF identity "
                f"`{report['benchmark']['sha256']}`; all systems match the same ordered 196 IDs."
            ),
            "",
            "## T1 detection",
            "",
            "| System | Overall F1 | Local F1 | Interprocedural F1 | Balanced accuracy | Answer rate |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, metrics in report["metrics"].items():
        lines.append(
            f"| {name} | {_fmt(metrics['overall']['f1'])} | "
            f"{_fmt(metrics['locus']['local']['f1'])} | "
            f"{_fmt(metrics['locus']['interprocedural']['f1'])} | "
            f"{_fmt(metrics['overall']['balanced_accuracy'])} | "
            f"{_fmt(metrics['overall']['answer_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## D1–D7 class strata",
            "",
            "The table reports full-coverage T1 within each gold class. Structured T3 precision/recall/F1 and confusion matrices are retained in `report.json`; binary-only static output cannot emit a D1–D7 class.",
            "",
            "| System | Class | n | Local | Interproc. | T1 F1 | Answer rate | Fragility |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for name in ("agent", "rag_reranker", "rag_dense", "plain_llm", "static_keyword"):
        for drift_type, row in report["metrics"][name]["class_strata"].items():
            fragile = (
                ", ".join(
                    locus
                    for locus, status in row["fragility"].items()
                    if status == "CI-fragile"
                )
                or "none"
            )
            lines.append(
                f"| {name} | {drift_type} | {row['support']} | {row['local_support']} | "
                f"{row['interprocedural_support']} | {_fmt(row['t1_within_gold_class']['f1'])} | "
                f"{_fmt(row['answer_rate'])} | {fragile} |"
            )
    agent_metrics = report["metrics"]["agent"]
    lines.extend(
        [
            "",
            "## Structured localization and classification",
            "",
            "| System | T3 macro-F1 | Program Acc@1 | Paragraph Acc@1 | Line Acc@1 | Line overlap |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name in ("agent", "plain_llm", "rag_dense", "rag_reranker", "oracle_slice"):
        row = report["metrics"][name]
        loc = row["t2_localization"]
        lines.append(
            f"| {name} | {_fmt(row['t3_classification']['macro_f1'])} | "
            f"{_fmt(loc['program']['accuracy@1'])} | {_fmt(loc['paragraph']['accuracy@1'])} | "
            f"{_fmt(loc['line']['accuracy@1'])} | {_fmt(loc['line']['overlap'])} |"
        )
    faith = report["faithfulness"]
    cal = report["calibration"]
    abstention = report["abstention"]
    t6 = report["t6"]
    lines.extend(
        [
            "",
            "## Agent faithfulness, calibration, and coverage",
            "",
            f"- Aggregate groundedness: {_fmt(faith['aggregate']['faithfulness'])} (n={faith['aggregate']['n']}).",
            "- Per-tier groundedness: "
            + ", ".join(
                f"Tier {tier} {_fmt(row['faithfulness'])} (n={row['n']})"
                for tier, row in faith["per_tier"].items()
            )
            + ".",
            f"- Clause evidence accuracy: {_fmt(faith['clause_evidence_accuracy'])}; code evidence accuracy: {_fmt(faith['code_evidence_accuracy'])}.",
            f"- Brier score: {_fmt(cal['brier_score'])}; ECE: {_fmt(cal['expected_calibration_error'])}.",
            f"- Answered {abstention['total_answered']}/196 ({_fmt(abstention['answer_rate'])}); abstained {abstention['total_abstained']}/196 ({_fmt(abstention['abstention_rate'])}).",
            "- Low coverage is part of the headline full-coverage result; unanswered rows are not discarded.",
            "",
            "## T6 temporal pairs",
            "",
            f"{t6['successes']} successes and {t6['failures']} failures across {t6['pairs']} pairs; paired accuracy {_fmt(t6['paired_accuracy'])}, exact 95% CI [{_fmt(t6['exact_95_ci'][0])}, {_fmt(t6['exact_95_ci'][1])}]. Status: **{t6['reporting_bar_status']}** because 20 pairs are required.",
            "",
            "## Cost and efficiency",
            "",
            "| System | Turns | Tokens recorded | Tool calls | Answer rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, row in report["cost_efficiency"]["systems"].items():
        lines.append(
            f"| {name} | {row['provider_turns']} | {row['token_count_total']} | "
            f"{row['tool_calls']} | {_fmt(row['answer_rate'])} |"
        )
    surface = report["frozen_decisions"]["surface_floor"]
    lines.extend(
        [
            "",
            "No dollar cost is estimated: provider runs were ChatGPT-authenticated and no metered billing record exists. Missing latency is reported as `not_recorded` in the JSON.",
            "",
            "## Error analysis and frozen decisions",
            "",
            "Reproducible category counts and representative IDs are in `error-analysis.json` and `error-analysis.md`.",
            "",
            f"The attacker surface floor remains **{surface['status']}** and is not a pass/fail gate. The attacker remains null anti-gaming evidence.",
            "",
            f"CI-fragile cells (n < {CI_FRAGILE_THRESHOLD}): "
            + ", ".join(report["ci_fragile_cells"])
            + ".",
            "",
            "The frozen CONTRACT bars are reported in `report.json`; they do not change this report's `EVALUABLE` status into a tuning checkpoint.",
            "",
        ]
    )
    _require(
        agent_metrics["overall"]["support"] == 196, "markdown metric support mismatch"
    )
    return "\n".join(lines)


def _error_markdown(errors: dict[str, Any]) -> str:
    lines = [f"# T5.4 Error Analysis — {errors['status']}", ""]
    if errors["status"] != "EVALUABLE":
        return "\n".join(lines + [f"- {issue}" for issue in errors.get("issues", [])])
    lines.extend([errors["method"], "", errors["root_cause_rule"], ""])
    for system_id, categories in errors["systems"].items():
        lines.extend(
            [
                f"## {system_id}",
                "",
                "| Category | Count | Applicable | Share | Representative IDs |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for name in sorted(REQUIRED_ERROR_CATEGORIES):
            row = categories[name]
            lines.append(
                f"| {name} | {row['count']} | {row['applicable_rows']} | "
                f"{_fmt(row['share_of_applicable_errors'])} | "
                f"{', '.join(row['representative_instance_ids']) or 'none'} |"
            )
        lines.extend(
            [
                "",
                "Failure-mode evidence: `"
                + json.dumps(categories["failure_mode_evidence"], sort_keys=True)
                + "`.",
                "",
            ]
        )
    return "\n".join(lines)


def write_headline_outputs(
    report: dict[str, Any],
    errors: dict[str, Any],
    *,
    output_dir: Path = M5,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "report.md").write_text(
        _report_markdown(report), encoding="utf-8", newline="\n"
    )
    (output_dir / "error-analysis.json").write_text(
        json.dumps(errors, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "error-analysis.md").write_text(
        _error_markdown(errors), encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--randomization-samples", type=int, default=20_000)
    parser.add_argument("--output-dir", type=Path, default=M5)
    args = parser.parse_args()
    report, errors = build_headline_outputs(
        bootstrap_resamples=args.bootstrap_resamples,
        randomization_samples=args.randomization_samples,
    )
    write_headline_outputs(report, errors, output_dir=args.output_dir)
    print(json.dumps({"status": report["status"], "issues": report["issues"]}))
    return 0 if report["status"] == "EVALUABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
