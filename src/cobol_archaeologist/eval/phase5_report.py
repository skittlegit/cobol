"""Fail-closed M5 report over the frozen agent and seven-baseline suite."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cobol_archaeologist.eval.metrics import evaluate
from cobol_archaeologist.eval.phase5 import (
    BinaryBaselineRecord,
    binary_detection,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord, TrajectoryAssessment

REQUIRED_BINARY = {
    "train_majority",
    "prevalence_random",
    "static_keyword",
    "attacker_with_bases",
}
REQUIRED_STRUCTURED = {"plain_llm", "rag_dense", "rag_reranker"}


class Phase5Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["EVALUABLE", "NOT_EVALUABLE"]
    issues: list[str]
    provenance: dict = {}
    systems: dict
    comparisons: dict
    decisions: dict


def _structured_binary(
    records: list[EvaluationRecord], system_id: str
) -> list[BinaryBaselineRecord]:
    return [
        BinaryBaselineRecord(
            instance_id=record.instance_id,
            system_id=system_id,
            gold_is_drift=record.gold.drift_type != "D7_conformant",
            predicted_is_drift=bool(
                not record.infrastructure_error
                and not record.abstained
                and record.prediction is not None
                and record.prediction.drift_type != "D7_conformant"
            ),
            score=record.confidence or 0.0,
            is_interprocedural=record.gold.code_locus.is_interprocedural,
            source_sha256=record.source_sha256,
        )
        for record in records
        if not record.infrastructure_error
    ]


def _paired_delta(
    left: list[BinaryBaselineRecord],
    right: list[BinaryBaselineRecord],
    *,
    seed: int,
    samples: int,
) -> tuple[float, float, float]:
    right_by_id = {row.instance_id: row for row in right}
    if len(right_by_id) != len(right):
        raise ValueError("paired baseline contains duplicate instance IDs")
    if {row.instance_id for row in left} != set(right_by_id):
        raise ValueError("paired baseline instance IDs do not align")
    pairs = [(row, right_by_id[row.instance_id]) for row in left]
    observed = binary_detection(left)["f1"] - binary_detection(right)["f1"]
    generator = random.Random(seed)
    deltas = []
    for _ in range(samples):
        indexes = [generator.randrange(len(pairs)) for _ in pairs]
        left_sample = [pairs[index][0] for index in indexes]
        right_sample = [pairs[index][1] for index in indexes]
        deltas.append(
            binary_detection(left_sample)["f1"] - binary_detection(right_sample)["f1"]
        )
    deltas.sort()
    return (
        observed,
        deltas[int(0.025 * (samples - 1))],
        deltas[int(0.975 * (samples - 1))],
    )


def build_phase5_report(
    *,
    agent: list[EvaluationRecord] | None,
    oracle_slice: list[EvaluationRecord] | None,
    structured: dict[str, list[EvaluationRecord]],
    binary: dict[str, list[BinaryBaselineRecord]],
    assessments: list[TrajectoryAssessment] = (),
    provenance: dict | None = None,
    benchmark_frozen: bool,
    annotation_complete: bool,
    resamples: int = 10_000,
) -> Phase5Report:
    issues = []
    if not benchmark_frozen:
        issues.append("T5.2 immutable benchmark manifest is absent")
    if not annotation_complete:
        issues.append("T5.1 annotation and verification evidence is incomplete")
    if not agent:
        issues.append("agent artifact is absent")
    if not oracle_slice:
        issues.append("oracle-slice artifact is absent")
    missing_binary = sorted(REQUIRED_BINARY - set(binary))
    missing_structured = sorted(REQUIRED_STRUCTURED - set(structured))
    if missing_binary:
        issues.append(f"missing binary baselines: {', '.join(missing_binary)}")
    if missing_structured:
        issues.append(f"missing structured baselines: {', '.join(missing_structured)}")
    if issues:
        return Phase5Report(
            status="NOT_EVALUABLE",
            issues=issues,
            provenance=provenance or {},
            systems={},
            comparisons={},
            decisions={},
        )

    agent_metrics = evaluate(agent, assessments)
    systems = {
        "agent": agent_metrics,
        "oracle_slice": evaluate(oracle_slice),
        **{name: evaluate(rows) for name, rows in structured.items()},
        **{
            name: {
                "overall": binary_detection(rows),
                "local": binary_detection(
                    [row for row in rows if not row.is_interprocedural]
                ),
                "interprocedural": binary_detection(
                    [row for row in rows if row.is_interprocedural]
                ),
            }
            for name, rows in binary.items()
        },
    }
    agent_binary = _structured_binary(agent, "agent")
    attacker_delta = _paired_delta(
        agent_binary,
        binary["attacker_with_bases"],
        seed=20260727,
        samples=resamples,
    )
    comparisons = {
        "agent_minus_attacker_with_bases_t1_f1": {
            "delta": attacker_delta[0],
            "bootstrap_95_ci": [attacker_delta[1], attacker_delta[2]],
        }
    }
    for offset, name in enumerate(("rag_dense", "rag_reranker", "oracle_slice"), 1):
        rows = oracle_slice if name == "oracle_slice" else structured[name]
        delta = _paired_delta(
            agent_binary,
            _structured_binary(rows, name),
            seed=20260727 + offset,
            samples=resamples,
        )
        comparisons[f"agent_minus_{name}_t1_f1"] = {
            "delta": delta[0],
            "bootstrap_95_ci": [delta[1], delta[2]],
        }
    decisions = {
        "surface_floor": {
            "required_margin": 0.10,
            "status": "VACATED",
            "met": None,
            "reason": (
                "T5.3 Finding A option (c): the registered attacker fit is "
                "all-zero and measures prevalence rather than surface cues"
            ),
        }
    }
    return Phase5Report(
        status="EVALUABLE",
        issues=[],
        provenance=provenance or {},
        systems=systems,
        comparisons=comparisons,
        decisions=decisions,
    )


def write_phase5_report(
    report: Phase5Report,
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    lines = [f"# M5 — {report.status}", ""]
    if report.issues:
        lines.extend(["## Blocking issues", ""])
        lines.extend(f"- {issue}" for issue in report.issues)
        lines.append("")
    if report.systems:
        lines.extend(["## Systems", ""])
        for name, metrics in report.systems.items():
            if name in {"agent", "oracle_slice", *REQUIRED_STRUCTURED}:
                row = metrics["overall"]["t1_detection"]
            else:
                row = metrics["overall"]
            lines.append(
                f"- **{name}:** T1 F1 {row['f1']:.4f}; "
                f"precision {row['precision']:.4f}; recall {row['recall']:.4f}; "
                f"answer rate {row['answer_rate']:.4f}."
            )
        lines.extend(
            [
                "",
                "## Paired decisions",
                "",
                "```json",
                json.dumps(
                    {
                        "comparisons": report.comparisons,
                        "decisions": report.decisions,
                    },
                    indent=2,
                ),
                "```",
                "",
            ]
        )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
