"""Fail-closed assembly of T5.3 artifacts projected from M4 plus targeted reruns."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from cobol_archaeologist.eval.live import ROOT
from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.eval.run import assess_run_validity
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.schemas import DriftInstance

TARGET_ID = "drift_000021"
M4_COMMIT = "357f4830b0cc64688bf957263f6c1af7217ffc28"
FROZEN_TEST = ROOT / "data" / "benchmark" / "v1" / "test.jsonl"
M4_DIR = ROOT / "data" / "eval" / "m4"
M5_DIR = ROOT / "data" / "eval" / "m5"


@dataclass(frozen=True)
class ProjectionSpec:
    system_id: str
    historical_system_id: str
    historical_records: Path
    historical_manifest: Path
    rerun_records: Path
    rerun_manifest: Path
    output_records: Path
    output_manifest: Path
    rerun_ids: frozenset[str]


def _load_jsonl(path: Path, model) -> list:
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index(records: Iterable[EvaluationRecord], *, label: str) -> dict[str, EvaluationRecord]:
    indexed = {record.instance_id: record for record in records}
    records = list(records) if not isinstance(records, list) else records
    if len(indexed) != len(records):
        raise ValueError(f"{label} contains duplicate instance IDs")
    return indexed


def _git_text(commit: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def confirm_m4_reranker_identity() -> dict[str, str]:
    """Prove the omitted M4 search mode from immutable runtime source."""

    manifest = json.loads((M4_DIR / "dense_rag.manifest.json").read_text("utf-8"))
    if manifest["repository_commit"] != M4_COMMIT:
        raise ValueError("M4 dense_rag manifest is not bound to the frozen M4 commit")
    live_source = _git_text(M4_COMMIT, "src/cobol_archaeologist/eval/codex_live.py")
    baseline_source = _git_text(M4_COMMIT, "src/cobol_archaeologist/eval/baselines.py")
    search_source = _git_text(M4_COMMIT, "src/cobol_archaeologist/rag/search.py")
    required = {
        "runner_default": "regulation_search=None",
        "context_call": "tools.search_regulations(clause_query)",
        "search_default": 'mode: str = "hybrid_rerank"',
    }
    bodies = {
        "runner_default": live_source,
        "context_call": baseline_source,
        "search_default": search_source,
    }
    missing = [name for name, needle in required.items() if needle not in bodies[name]]
    if missing:
        raise ValueError(f"M4 hybrid-rerank source proof failed: {', '.join(missing)}")
    return {
        "repository_commit": M4_COMMIT,
        "runner_default": required["runner_default"],
        "context_call": required["context_call"],
        "search_default": required["search_default"],
        "conclusion": "search.mode == hybrid_rerank",
    }


def _rebind(record: EvaluationRecord, gold: DriftInstance, system_id: str) -> EvaluationRecord:
    payload = record.model_dump(mode="json")
    payload["gold"] = gold.model_dump(mode="json")
    payload["instance_id"] = gold.instance_id
    payload["system_id"] = system_id
    return EvaluationRecord.model_validate(payload)


def _assemble(spec: ProjectionSpec, frozen_rows: list[DriftInstance]) -> dict[str, Any]:
    historical = _load_jsonl(spec.historical_records, EvaluationRecord)
    rerun = _load_jsonl(spec.rerun_records, EvaluationRecord)
    historical_by_id = _index(historical, label=str(spec.historical_records))
    rerun_by_id = _index(rerun, label=str(spec.rerun_records))
    frozen_ids = {row.instance_id for row in frozen_rows}
    if not spec.rerun_ids <= frozen_ids:
        raise ValueError(f"{spec.system_id} rerun IDs are outside frozen v1")
    if set(rerun_by_id) != set(spec.rerun_ids):
        raise ValueError(f"{spec.system_id} targeted rerun has the wrong ID set")
    if not frozen_ids <= set(historical_by_id):
        raise ValueError(f"{spec.system_id} M4 artifact lacks surviving v1 IDs")

    historical_manifest = json.loads(spec.historical_manifest.read_text("utf-8"))
    rerun_manifest = json.loads(spec.rerun_manifest.read_text("utf-8"))
    historical_keys = set(historical_manifest["completed_run_keys"])
    rerun_keys = set(rerun_manifest["completed_run_keys"])
    if any(record.run_key not in historical_keys for record in historical):
        raise ValueError(f"{spec.system_id} M4 record/manifest run-key mismatch")
    if any(record.run_key not in rerun_keys for record in rerun):
        raise ValueError(f"{spec.system_id} rerun record/manifest run-key mismatch")

    assembled: list[EvaluationRecord] = []
    reused_ids: list[str] = []
    for gold in frozen_rows:
        if gold.instance_id in spec.rerun_ids:
            record = rerun_by_id[gold.instance_id]
        else:
            record = historical_by_id[gold.instance_id]
            current_sha = materialize(gold).source_sha256
            if record.source_sha256 != current_sha:
                raise ValueError(
                    f"{spec.system_id} source identity mismatch for {gold.instance_id}"
                )
            reused_ids.append(gold.instance_id)
        rebound = _rebind(record, gold, spec.system_id)
        if not rebound.abstained and (
            rebound.verification is None or not rebound.verification.verified
        ):
            raise ValueError(f"{spec.system_id} emitted an unverified finding")
        if rebound.infrastructure_error:
            raise ValueError(f"{spec.system_id} contains an infrastructure failure")
        assembled.append(rebound)

    validity = assess_run_validity(assembled, system_id=spec.system_id)
    if validity.status != "VALID":
        raise ValueError(f"{spec.system_id} projection is {validity.status}")
    spec.output_records.parent.mkdir(parents=True, exist_ok=True)
    spec.output_records.write_text(
        "".join(record.model_dump_json() + "\n" for record in assembled),
        encoding="utf-8",
        newline="\n",
    )
    projection: dict[str, Any] = {
        "artifact_kind": "t5.3_reuse_projection_v1",
        "system_id": spec.system_id,
        "split_path": FROZEN_TEST.relative_to(ROOT).as_posix(),
        "split_sha256": _sha256(FROZEN_TEST),
        "total": len(assembled),
        "completed_run_keys": [record.run_key for record in assembled],
        "validity": validity.model_dump(mode="json"),
        "reuse": {
            "historical_system_id": spec.historical_system_id,
            "historical_records": spec.historical_records.relative_to(ROOT).as_posix(),
            "historical_manifest": spec.historical_manifest.relative_to(ROOT).as_posix(),
            "historical_manifest_sha256": _sha256(spec.historical_manifest),
            "reused_rows": len(reused_ids),
            "reused_instance_ids_sha256": hashlib.sha256(
                "\n".join(reused_ids).encode()
            ).hexdigest(),
        },
        "rerun": {
            "records": spec.rerun_records.relative_to(ROOT).as_posix(),
            "manifest": spec.rerun_manifest.relative_to(ROOT).as_posix(),
            "manifest_sha256": _sha256(spec.rerun_manifest),
            "rows": len(spec.rerun_ids),
            "instance_ids": sorted(spec.rerun_ids),
        },
    }
    if spec.system_id == "rag_reranker":
        projection["search_identity"] = confirm_m4_reranker_identity()
    spec.output_manifest.write_text(
        json.dumps(projection, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return projection


def projection_specs() -> tuple[ProjectionSpec, ...]:
    real_ids = frozenset(
        row.instance_id
        for row in _load_jsonl(FROZEN_TEST, DriftInstance)
        if row.provenance.source == "real_curated"
    )
    if len(real_ids) != 43:
        raise ValueError(f"expected 43 real-curated rows, found {len(real_ids)}")
    return (
        ProjectionSpec(
            "agent",
            "agent",
            M4_DIR / "agent.jsonl",
            M4_DIR / "agent.manifest.json",
            M5_DIR / "agent-rerun" / "full" / "agent.jsonl",
            M5_DIR / "agent-rerun" / "full" / "agent.manifest.json",
            M5_DIR / "agent-rerun" / "agent.jsonl",
            M5_DIR / "agent-rerun" / "agent.manifest.json",
            frozenset({TARGET_ID}),
        ),
        ProjectionSpec(
            "rag_reranker",
            "dense_rag",
            M4_DIR / "dense_rag.jsonl",
            M4_DIR / "dense_rag.manifest.json",
            M5_DIR / "rag_reranker-rerun" / "full" / "rag_reranker.jsonl",
            M5_DIR / "rag_reranker-rerun" / "full" / "rag_reranker.manifest.json",
            M5_DIR / "rag_reranker" / "rag_reranker.jsonl",
            M5_DIR / "rag_reranker" / "rag_reranker.manifest.json",
            frozenset({TARGET_ID}),
        ),
        ProjectionSpec(
            "oracle_slice",
            "oracle_slice",
            M4_DIR / "oracle_slice.jsonl",
            M4_DIR / "oracle_slice.manifest.json",
            M5_DIR / "oracle_slice-rerun" / "full" / "oracle_slice.jsonl",
            M5_DIR / "oracle_slice-rerun" / "full" / "oracle_slice.manifest.json",
            M5_DIR / "oracle_slice-rerun" / "oracle_slice.jsonl",
            M5_DIR / "oracle_slice-rerun" / "oracle_slice.manifest.json",
            real_ids,
        ),
    )


def assemble_phase5_projections() -> list[dict[str, Any]]:
    frozen_rows = _load_jsonl(FROZEN_TEST, DriftInstance)
    if len(frozen_rows) != 196:
        raise ValueError(f"expected 196 frozen rows, found {len(frozen_rows)}")
    return [_assemble(spec, frozen_rows) for spec in projection_specs()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    for result in assemble_phase5_projections():
        print(json.dumps({"system": result["system_id"], "validity": result["validity"]["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
