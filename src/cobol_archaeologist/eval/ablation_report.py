"""Fail-closed paired reporting for the frozen T5.5A supplement."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from cobol_archaeologist.eval.ablations import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CONFIGURATION_IDS,
    CONFIGURATIONS,
    DEFINITION_PATH,
    OUTPUT_ROOT,
    VERSIONING_DISPOSITION,
    load_frozen_panel,
)
from cobol_archaeologist.eval.metrics import classification, detection, evaluate
from cobol_archaeologist.eval.run import RunManifest
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.eval.statistics import paired_bootstrap_delta
from cobol_archaeologist.eval.trajectory import assess_all

REPORT_JSON = OUTPUT_ROOT / "report.json"
REPORT_MD = OUTPUT_ROOT / "report.md"
LOCUS_NAMES: tuple[Literal["overall", "local", "interprocedural"], ...] = (
    "overall",
    "local",
    "interprocedural",
)


def _load_records(path: Path) -> list[EvaluationRecord]:
    return [
        EvaluationRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _balanced_accuracy(records: Sequence[EvaluationRecord]) -> float:
    positives = [row for row in records if row.gold.drift_type != "D7_conformant"]
    negatives = [row for row in records if row.gold.drift_type == "D7_conformant"]
    sensitivity = (
        sum(
            not row.abstained
            and row.prediction is not None
            and row.prediction.drift_type != "D7_conformant"
            for row in positives
        )
        / len(positives)
        if positives
        else 0.0
    )
    specificity = (
        sum(
            not row.abstained
            and row.prediction is not None
            and row.prediction.drift_type == "D7_conformant"
            for row in negatives
        )
        / len(negatives)
        if negatives
        else 0.0
    )
    return (sensitivity + specificity) / 2


def _t1(records: Sequence[EvaluationRecord]) -> dict[str, Any]:
    result = detection(records)
    return {
        **result,
        "balanced_accuracy": _balanced_accuracy(records),
        "support": len(records),
        "answered": sum(not row.abstained for row in records),
        "abstained": sum(row.abstained for row in records),
    }


def _stratum(
    records: Sequence[EvaluationRecord],
    locus: Literal["overall", "local", "interprocedural"],
) -> list[EvaluationRecord]:
    if locus == "overall":
        return list(records)
    interprocedural = locus == "interprocedural"
    return [
        row
        for row in records
        if row.gold.code_locus.is_interprocedural == interprocedural
    ]


def _efficiency(records: Sequence[EvaluationRecord]) -> dict[str, Any]:
    trajectories = [trace.trajectory for row in records for trace in row.agent_hunts]
    calls = [call for trajectory in trajectories for call in trajectory.steps]
    responses = [
        response for trajectory in trajectories for response in trajectory.model_responses
    ]
    return {
        "provider_turns": len(responses),
        "model_calls": len(responses),
        "tokens": sum(response.token_count for response in responses),
        "tool_calls": len(calls),
        "successful_tool_calls": sum(call.error is None for call in calls),
        "cobol_execution_calls": sum(
            call.tool == "run_cobol" and call.error is None for call in calls
        ),
        "retrieval_calls": sum(
            call.tool == "search_regulations" and call.error is None for call in calls
        ),
        "recorded_tool_latency_ms": sum(call.latency_ms for call in calls),
        "provider_wall_time": "not_recorded",
        "monetary_cost": "not_recorded",
    }


def _system_metrics(records: list[EvaluationRecord]) -> dict[str, Any]:
    assessments = assess_all(records)
    assessed = {row.instance_id: row for row in assessments}
    answered = [row for row in records if not row.abstained]
    evaluated = evaluate(records, assessments)
    class_result = classification(records)
    return {
        "t1": {locus: _t1(_stratum(records, locus)) for locus in LOCUS_NAMES},
        "class_strata": {
            drift_type: {
                "support": sum(row.gold.drift_type == drift_type for row in records),
                "f1": values["f1"],
                "precision": values["precision"],
                "recall": values["recall"],
                "answer_rate": (
                    sum(
                        row.gold.drift_type == drift_type and not row.abstained
                        for row in records
                    )
                    / sum(row.gold.drift_type == drift_type for row in records)
                ),
                "fragility": "CI-fragile",
            }
            for drift_type, values in class_result["per_class"].items()
        },
        "t2_localization": evaluated["overall"]["t2_localization"],
        "t3_classification": evaluated["overall"]["t3_classification"],
        "faithfulness": {
            **evaluated["overall"]["t4_faithfulness"],
            "clause_evidence_accuracy": (
                sum(row.prediction.regulation_clause == row.gold.regulation_clause for row in answered)
                / len(answered)
                if answered
                else None
            ),
            "code_evidence_accuracy": (
                sum(assessed[row.instance_id].code_fact_ok for row in answered)
                / len(answered)
                if answered
                else None
            ),
        },
        "t6_directional": evaluated["overall"]["t6_versioned_judgment"],
        "efficiency": _efficiency(records),
        "abstention_reasons": dict(
            Counter(row.abstention_reason or "answered" for row in records)
        ),
    }


def _paired(
    ablation: Sequence[EvaluationRecord],
    control: Sequence[EvaluationRecord],
    locus: Literal["overall", "local", "interprocedural"],
) -> dict[str, Any]:
    left = _stratum(ablation, locus)
    control_by_id = {row.instance_id: row for row in control}
    right = [control_by_id[row.instance_id] for row in left]

    def metric(rows: Sequence[object]) -> float:
        return detection(rows)["f1"]  # type: ignore[arg-type]

    delta, low, high = paired_bootstrap_delta(
        left,
        right,
        metric,
        resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
    )
    return {
        "locus": locus,
        "paired_rows": len(left),
        "ablation_f1": detection(left)["f1"],
        "control_f1": detection(right)["f1"],
        "delta_f1_ablation_minus_control": delta,
        "paired_bootstrap_95_ci": [low, high],
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }


def build_report() -> dict[str, Any]:
    panel = load_frozen_panel()
    definition = json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))
    definition_without_identity = {
        key: value for key, value in definition.items() if key != "identity_sha256"
    }
    reproduced_definition_identity = hashlib.sha256(
        json.dumps(
            definition_without_identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    if definition["identity_sha256"] != reproduced_definition_identity:
        raise ValueError("T5.5A definition identity does not reproduce")
    records_by_configuration: dict[str, list[EvaluationRecord]] = {}
    manifests: dict[str, RunManifest] = {}
    artifact_identities: dict[str, Any] = {}
    for configuration_id in CONFIGURATION_IDS:
        root = OUTPUT_ROOT / configuration_id
        records_path = root / "agent.jsonl"
        manifest_path = root / "agent.manifest.json"
        smoke_manifest_path = root / "smoke" / "agent.manifest.json"
        records = _load_records(records_path)
        manifest = RunManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        smoke_manifest = RunManifest.model_validate_json(
            smoke_manifest_path.read_text(encoding="utf-8")
        )
        ids = [row.instance_id for row in records]
        if ids != panel.instance_ids:
            raise ValueError(f"{configuration_id} IDs/order do not match panel")
        if any(row.system_id != configuration_id for row in records):
            raise ValueError(f"{configuration_id} record identity mismatch")
        if (
            manifest.configuration_id != configuration_id
            or manifest.experiment_id != panel.experiment_id
            or manifest.panel_identity_sha256 != panel.identity_sha256
            or manifest.definition_sha256 != definition["identity_sha256"]
            or manifest.run_mode != "full"
            or manifest.validity is None
            or manifest.validity.status != "VALID"
            or manifest.infrastructure_failures
        ):
            raise ValueError(f"{configuration_id} manifest is not a valid frozen full run")
        if (
            smoke_manifest.configuration_id != configuration_id
            or smoke_manifest.panel_identity_sha256 != panel.identity_sha256
            or smoke_manifest.smoke_instance_ids != panel.smoke_instance_ids
            or smoke_manifest.run_mode != "smoke"
            or smoke_manifest.total != len(panel.smoke_instance_ids)
            or smoke_manifest.validity is None
            or smoke_manifest.validity.status != "VALID"
            or smoke_manifest.infrastructure_failures
        ):
            raise ValueError(f"{configuration_id} smoke manifest is not valid")
        records_by_configuration[configuration_id] = records
        manifests[configuration_id] = manifest
        artifact_identities[configuration_id] = {
            "records_sha256": _sha256(records_path),
            "manifest_sha256": _sha256(manifest_path),
            "smoke_manifest_sha256": _sha256(smoke_manifest_path),
            "repository_commit": manifest.repository_commit,
        }
    control = records_by_configuration["control"]
    metrics = {
        configuration_id: _system_metrics(records)
        for configuration_id, records in records_by_configuration.items()
    }
    paired = {
        configuration_id: {
            locus: _paired(records_by_configuration[configuration_id], control, locus)
            for locus in LOCUS_NAMES
        }
        for configuration_id in CONFIGURATION_IDS
        if configuration_id != "control"
    }
    return {
        "experiment_id": panel.experiment_id,
        "status": "EVALUABLE",
        "supplemental_only": True,
        "m4_reopened": False,
        "m5_reopened": False,
        "panel": panel.model_dump(mode="json"),
        "definition_identity_sha256": definition["identity_sha256"],
        "configurations": {
            key: CONFIGURATIONS[key].model_dump(mode="json")
            for key in CONFIGURATION_IDS
        },
        "versioning": VERSIONING_DISPOSITION,
        "metrics": metrics,
        "paired_comparisons": paired,
        "interpretation_rule": (
            "Report quantitative paired effects, uncertainty, class/locus consistency, "
            "coverage, and faithfulness without post-result categorical thresholds."
        ),
        "claim_limits": [
            "The 71-row supplemental panel is not the full 196-row headline test.",
            "The contribution of version awareness was not independently estimated.",
            "Small class/locus cells are CI-fragile.",
            "No monetary cost or unrecorded provider latency is inferred.",
        ],
        "manifest_commits": {
            key: manifest.repository_commit for key, manifest in manifests.items()
        },
        "artifact_identities": artifact_identities,
    }


def _fmt(value: Any) -> str:
    return "not recorded" if isinstance(value, str) else f"{value:.4f}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# T5.5A core ablation supplement",
        "",
        f"Status: **{report['status']}**. M4 and M5 remain closed.",
        "",
        "| Configuration | Overall F1 | Local F1 | Interproc F1 | Answer rate | Groundedness | Tokens | Tool calls |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for configuration_id in CONFIGURATION_IDS:
        metrics = report["metrics"][configuration_id]
        lines.append(
            "| "
            + " | ".join(
                (
                    configuration_id,
                    _fmt(metrics["t1"]["overall"]["f1"]),
                    _fmt(metrics["t1"]["local"]["f1"]),
                    _fmt(metrics["t1"]["interprocedural"]["f1"]),
                    _fmt(metrics["t1"]["overall"]["answer_rate"]),
                    _fmt(metrics["faithfulness"]["aggregate"]["faithfulness"]),
                    str(metrics["efficiency"]["tokens"]),
                    str(metrics["efficiency"]["tool_calls"]),
                )
            )
            + " |"
        )
    lines.extend(["", "## Paired effects", ""])
    for configuration_id, comparisons in report["paired_comparisons"].items():
        lines.append(f"### {configuration_id}")
        lines.append("")
        for locus, comparison in comparisons.items():
            low, high = comparison["paired_bootstrap_95_ci"]
            lines.append(
                f"- {locus}: delta F1 {comparison['delta_f1_ablation_minus_control']:.4f}; "
                f"paired 95% CI [{low:.4f}, {high:.4f}], n={comparison['paired_rows']}."
            )
        lines.append("")
    lines.extend(
        [
            "## Versioning disposition",
            "",
            "`NOT_INDEPENDENTLY_ABLATABLE`: " + report["versioning"]["reason"],
            "",
            report["versioning"]["claim_limit"],
            "",
            "This is a 71-row supplemental panel, not the frozen 196-row headline test.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report() -> dict[str, Any]:
    report = build_report()
    REPORT_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return report


def main() -> int:
    report = write_report()
    print(json.dumps({"status": report["status"], "report": str(REPORT_JSON)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
