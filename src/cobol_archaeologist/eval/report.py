"""M4 go/no-go report construction with fail-closed readiness checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cobol_archaeologist.eval.calibration import calibration
from cobol_archaeologist.eval.metrics import detection, evaluate
from cobol_archaeologist.eval.schemas import EvaluationRecord, TrajectoryAssessment
from cobol_archaeologist.eval.statistics import (
    paired_bootstrap_delta,
    paired_randomization_p,
)


class M4Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["GO", "NO_GO", "NOT_EVALUABLE"]
    issues: list[str]
    metrics: dict
    decisions: dict


def _aligned(
    left: list[EvaluationRecord],
    right: list[EvaluationRecord],
) -> tuple[list[EvaluationRecord], list[EvaluationRecord]]:
    right_by_id = {record.instance_id: record for record in right}
    left_rows = [record for record in left if record.instance_id in right_by_id]
    return left_rows, [right_by_id[record.instance_id] for record in left_rows]


def _verdict_correct(record: EvaluationRecord) -> bool:
    if record.infrastructure_error or record.abstained or record.prediction is None:
        return False
    return (
        record.prediction.drift_type != "D7_conformant"
    ) == (record.gold.drift_type != "D7_conformant")


def build_m4_report(
    *,
    agent: list[EvaluationRecord] | None,
    dense_rag: list[EvaluationRecord] | None,
    oracle_slice: list[EvaluationRecord] | None,
    assessments: list[TrajectoryAssessment] = (),
    verifier_labels_complete: bool,
    resamples: int = 10_000,
) -> M4Report:
    issues: list[str] = []
    for name, records in (
        ("agent", agent),
        ("dense-RAG", dense_rag),
        ("oracle-slice", oracle_slice),
    ):
        if not records:
            issues.append(f"{name} evaluation artifact is missing")
    if not verifier_labels_complete:
        issues.append("50-pair verifier human labels are incomplete")
    if issues:
        return M4Report(
            status="NOT_EVALUABLE",
            issues=issues,
            metrics={},
            decisions={},
        )

    agent_metrics = evaluate(agent, assessments)
    dense_metrics = evaluate(dense_rag)
    oracle_metrics = evaluate(oracle_slice)
    t6 = agent_metrics["overall"]["t6_versioned_judgment"]
    if not t6["reporting_bar_evaluable"]:
        issues.append(
            f"T6 has {t6['pairs']} verdict-flipping pairs; at least 20 required"
        )
    if any(record.infrastructure_error for record in agent):
        issues.append("agent artifact contains infrastructure failures")

    agent_inter = [r for r in agent if r.gold.code_locus.is_interprocedural]
    dense_inter = [r for r in dense_rag if r.gold.code_locus.is_interprocedural]
    oracle_inter = [r for r in oracle_slice if r.gold.code_locus.is_interprocedural]
    agent_dense, dense_paired = _aligned(agent_inter, dense_inter)
    agent_oracle, oracle_paired = _aligned(agent_inter, oracle_inter)
    if not agent_dense or len(agent_dense) != len(agent_inter):
        issues.append("agent/dense interprocedural rows are not fully paired")
    if not agent_oracle or len(agent_oracle) != len(agent_inter):
        issues.append("agent/oracle interprocedural rows are not fully paired")
    if issues:
        return M4Report(
            status="NOT_EVALUABLE",
            issues=issues,
            metrics={
                "agent": agent_metrics,
                "dense_rag": dense_metrics,
                "oracle_slice": oracle_metrics,
                "calibration": calibration(agent, assessments),
            },
            decisions={},
        )

    metric = lambda rows: detection(rows)["f1"]
    dense_delta, dense_low, dense_high = paired_bootstrap_delta(
        agent_dense,
        dense_paired,
        metric,
        resamples=resamples,
    )
    oracle_delta, oracle_low, oracle_high = paired_bootstrap_delta(
        agent_oracle,
        oracle_paired,
        metric,
        resamples=resamples,
    )
    p_value = paired_randomization_p(
        [_verdict_correct(record) for record in agent_dense],
        [_verdict_correct(record) for record in dense_paired],
        samples=max(resamples, 20_000),
    )
    overall_f1 = agent_metrics["overall"]["t1_detection"]["f1"]
    bars = {
        "overall_f1": {
            "observed": overall_f1,
            "required": 0.70,
            "met": overall_f1 >= 0.70,
        },
        "interprocedural_vs_dense": {
            "delta": dense_delta,
            "bootstrap_95_ci": [dense_low, dense_high],
            "paired_p": p_value,
            "met": dense_delta >= 0.10 and dense_low > 0 and p_value < 0.05,
        },
        "oracle_slice_deconfounder": {
            "delta": oracle_delta,
            "bootstrap_95_ci": [oracle_low, oracle_high],
            "loop_adds_value": oracle_delta > 0,
        },
        "t6_reporting_bar": t6,
    }
    go = bars["overall_f1"]["met"] and bars["interprocedural_vs_dense"]["met"]
    return M4Report(
        status="GO" if go else "NO_GO",
        issues=[],
        metrics={
            "agent": agent_metrics,
            "dense_rag": dense_metrics,
            "oracle_slice": oracle_metrics,
            "calibration": calibration(agent, assessments),
        },
        decisions=bars,
    )


def write_report(report: M4Report, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    lines = [f"# M4 — {report.status}", ""]
    if report.issues:
        lines.extend(["## Blocking issues", ""])
        lines.extend(f"- {issue}" for issue in report.issues)
        lines.append("")
    if report.decisions:
        lines.extend(
            [
                "## Decisions",
                "",
                "```json",
                json.dumps(report.decisions, indent=2, default=str),
                "```",
                "",
            ]
        )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
