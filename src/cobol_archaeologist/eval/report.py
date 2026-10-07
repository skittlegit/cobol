"""Score the detector against the frozen gates and write the decision.

    python -m cobol_archaeologist.eval.report --split test

Reads ``data/eval/<split>/{detector,rag_reranker}.jsonl`` and
``data/eval/temporal/detector.jsonl``; writes ``data/eval/<split>/report.json``
and ``report.md``.  The decision is:

* ``NOT_EVALUABLE`` - a required row is missing or failed on infrastructure;
* ``GO``            - every gate passes;
* ``NO_GO``         - otherwise.

Gates are fixed in ``GATES`` and are never changed after results are seen.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cobol_archaeologist.eval.metrics import (
    balanced_accuracy,
    classification,
    confusion_matrix,
    detection,
    faithfulness,
    localization,
    paired_f1_comparison,
)
from cobol_archaeologist.eval.runner import (
    BENCHMARK,
    EVAL_ROOT,
    Split,
    load_split,
    results_path,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.eval.statistics import exact_binomial_interval
from cobol_archaeologist.eval.trajectory import assess_all

GATES = {
    "t1_f1": 0.70,
    "balanced_accuracy": 0.65,
    "answer_rate": 0.60,
    "answered_accuracy": 0.80,
    "interprocedural_delta_f1": 0.10,
    "interprocedural_p": 0.05,
    "temporal_paired_accuracy": 0.70,
    "temporal_min_pairs": 20,
}
STATISTICS = {
    "bootstrap_resamples": 10_000,
    "randomization_samples": 20_000,
    "seed": 20260823,
}


def load_records(path: Path) -> list[EvaluationRecord]:
    if not path.exists():
        return []
    return [
        EvaluationRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _coverage(
    records: Sequence[EvaluationRecord], expected: Sequence[str]
) -> list[str]:
    have = {record.instance_id for record in records if not record.infrastructure_error}
    return [instance_id for instance_id in expected if instance_id not in have]


def current_records(
    split: Split, system: str, records: Sequence[EvaluationRecord]
) -> list[EvaluationRecord]:
    """Keep records whose run_key matches the current method identity."""

    from cobol_archaeologist.eval import codex, runner

    identity = runner.method_identity(system, codex.runtime_identity())
    rows = {row.instance_id: row for row in load_split(split)}
    current = []
    for record in records:
        row = rows.get(record.instance_id)
        if row is None:
            continue
        source = runner.materialize_row(row, split)
        if record.run_key == runner.run_key(identity, row, source.source_sha256):
            current.append(record)
    return current


def temporal_score(records: Sequence[EvaluationRecord]) -> dict[str, Any]:
    pairs = json.loads(
        (BENCHMARK / "temporal" / "pairs.json").read_text(encoding="utf-8")
    )
    by_id = {record.instance_id: record for record in records}

    def correct(instance_id: str) -> bool:
        record = by_id.get(instance_id)
        return bool(
            record
            and not record.infrastructure_error
            and not record.abstained
            and record.prediction is not None
            and (record.prediction.drift_type == "D7_conformant")
            == (record.gold.drift_type == "D7_conformant")
        )

    results = {
        pid: all(correct(m) for m in pair["members"]) for pid, pair in pairs.items()
    }
    successes = sum(results.values())
    total = len(results)
    low, high = exact_binomial_interval(successes, total) if total else (None, None)
    return {
        "pairs": total,
        "successes": successes,
        "paired_accuracy": successes / total if total else 0.0,
        "exact_95_ci": [low, high],
        "per_pair": results,
    }


def summarize(records: Sequence[EvaluationRecord]) -> dict[str, Any]:
    strata = {
        "local": [r for r in records if not r.gold.code_locus.is_interprocedural],
        "interprocedural": [r for r in records if r.gold.code_locus.is_interprocedural],
    }
    return {
        "rows": len(records),
        "t1": {**detection(records), "balanced_accuracy": balanced_accuracy(records)},
        "t2": localization(records),
        "t3": classification(records),
        "t4_faithfulness": faithfulness(records, assess_all(list(records))),
        "confusion": confusion_matrix(records),
        "strata": {
            name: {**detection(rows), "balanced_accuracy": balanced_accuracy(rows)}
            for name, rows in strata.items()
        },
    }


def build_report(split: Split) -> dict[str, Any]:
    expected = [row.instance_id for row in load_split(split)]
    detector = load_records(results_path(split, "detector"))
    baseline = load_records(results_path(split, "rag_reranker"))
    temporal = load_records(results_path("temporal", "detector"))
    temporal_expected = [row.instance_id for row in load_split("temporal")]
    missing = {
        "detector": _coverage(detector, expected),
        "rag_reranker": _coverage(baseline, expected),
        "temporal": _coverage(temporal, temporal_expected),
    }
    report: dict[str, Any] = {
        "split": split,
        "gates": GATES,
        "statistics": STATISTICS,
        "missing_or_failed": {k: v for k, v in missing.items() if v},
    }
    if split == "test":
        if not expected:
            report["decision"] = "NOT_EVALUABLE"
            report["reason"] = "the test split has no rows yet"
            return report
        if any(missing.values()):
            report["decision"] = "NOT_EVALUABLE"
            report["reason"] = "required rows are missing or failed on infrastructure"
            return report
    else:
        # Development scoring: only records from the current method version,
        # on rows both systems answered without an infrastructure failure.
        # Gates are shown for reference only.
        detector = current_records(split, "detector", detector)
        baseline = current_records(split, "rag_reranker", baseline)
        temporal = current_records("temporal", "detector", temporal)
        detector_ids = {r.instance_id for r in detector if not r.infrastructure_error}
        baseline_ids = {r.instance_id for r in baseline if not r.infrastructure_error}
        detector = [r for r in detector if r.instance_id in detector_ids]
        paired = detector_ids & baseline_ids
        baseline = [r for r in baseline if r.instance_id in paired]
        temporal = [r for r in temporal if not r.infrastructure_error]
        report["scored_rows"] = len(detector)
        if not detector:
            report["decision"] = "NOT_EVALUABLE"
            report["reason"] = "no detector results on this split"
            return report
    detector_summary = summarize(detector)
    paired_detector = [
        r for r in detector if r.instance_id in {b.instance_id for b in baseline}
    ]
    comparison = (
        paired_f1_comparison(
            paired_detector, baseline, locus="interprocedural", **STATISTICS
        )
        if any(r.gold.code_locus.is_interprocedural for r in baseline)
        else None
    )
    temporal_result = temporal_score(temporal)
    t1 = detector_summary["t1"]
    unverified = sum(
        1
        for record in detector
        if not record.abstained
        and not record.infrastructure_error
        and (record.verification is None or not record.verification.verified)
    )
    checks = {
        "t1_f1": t1["f1"] >= GATES["t1_f1"],
        "balanced_accuracy": t1["balanced_accuracy"] >= GATES["balanced_accuracy"],
        "answer_rate": t1["answer_rate"] >= GATES["answer_rate"],
        "answered_accuracy": t1["answered_accuracy"] >= GATES["answered_accuracy"],
        "interprocedural_advantage": comparison is not None
        and (
            comparison["delta_f1"] >= GATES["interprocedural_delta_f1"]
            and comparison["bootstrap_95_ci"][0] > 0
            and comparison["paired_randomization_p"] < GATES["interprocedural_p"]
        ),
        "temporal_paired_accuracy": (
            temporal_result["pairs"] >= GATES["temporal_min_pairs"]
            and temporal_result["paired_accuracy"] >= GATES["temporal_paired_accuracy"]
        ),
        "zero_unverified_findings": unverified == 0,
    }
    report.update(
        {
            "decision": (
                ("GO" if all(checks.values()) else "NO_GO")
                if split == "test"
                else "DEV_ONLY"
            ),
            "gate_results": checks,
            "detector": detector_summary,
            "rag_reranker": summarize(baseline) if baseline else None,
            "interprocedural_comparison": comparison,
            "temporal": temporal_result,
        }
    )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Detector report: {report['split']} split", ""]
    lines.append(f"**Decision: {report['decision']}**")
    lines.append("")
    if report["decision"] == "NOT_EVALUABLE":
        lines.append(report["reason"])
        for system, ids in report["missing_or_failed"].items():
            lines.append(f"- {system}: {len(ids)} rows missing/failed")
        return "\n".join(lines) + "\n"
    t1 = report["detector"]["t1"]
    comparison = report["interprocedural_comparison"] or {
        "delta_f1": float("nan"),
        "bootstrap_95_ci": [float("nan"), float("nan")],
        "paired_randomization_p": float("nan"),
        "paired_rows": 0,
    }
    temporal = report["temporal"]
    rows = [
        ("T1 F1", f"{t1['f1']:.3f}", f">= {GATES['t1_f1']}", "t1_f1"),
        (
            "Balanced accuracy",
            f"{t1['balanced_accuracy']:.3f}",
            f">= {GATES['balanced_accuracy']}",
            "balanced_accuracy",
        ),
        (
            "Answer rate",
            f"{t1['answer_rate']:.3f}",
            f">= {GATES['answer_rate']}",
            "answer_rate",
        ),
        (
            "Answered accuracy",
            f"{t1['answered_accuracy']:.3f}",
            f">= {GATES['answered_accuracy']}",
            "answered_accuracy",
        ),
        (
            "Interprocedural F1 vs rag_reranker",
            (
                f"{comparison['delta_f1']:+.3f} "
                f"(CI {comparison['bootstrap_95_ci'][0]:.3f}.."
                f"{comparison['bootstrap_95_ci'][1]:.3f}, "
                f"p={comparison['paired_randomization_p']:.4f}, "
                f"n={comparison['paired_rows']})"
            ),
            ">= +0.10, CI > 0, p < 0.05",
            "interprocedural_advantage",
        ),
        (
            "Temporal paired accuracy",
            f"{temporal['successes']}/{temporal['pairs']} = {temporal['paired_accuracy']:.3f}",
            f">= {GATES['temporal_paired_accuracy']} on >= {GATES['temporal_min_pairs']} pairs",
            "temporal_paired_accuracy",
        ),
        (
            "Unverified findings",
            "0" if report["gate_results"]["zero_unverified_findings"] else ">0",
            "0",
            "zero_unverified_findings",
        ),
    ]
    lines += ["| Gate | Measured | Required | Pass |", "| --- | --- | --- | --- |"]
    for name, measured, required, key in rows:
        lines.append(
            f"| {name} | {measured} | {required} | "
            f"{'yes' if report['gate_results'][key] else 'NO'} |"
        )
    lines += ["", "## Confusion matrix (detector)", ""]
    matrix = report["detector"]["confusion"]
    columns = list(next(iter(matrix.values())))
    lines.append(
        "| gold \\ predicted | "
        + " | ".join(c[:2] if c != "ABSTAIN" else "ABST" for c in columns)
        + " |"
    )
    lines.append("| --- |" + " --- |" * len(columns))
    for gold, row in matrix.items():
        lines.append(f"| {gold} | " + " | ".join(str(row[c]) for c in columns) + " |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=("train", "dev", "test"), default="test")
    args = parser.parse_args(argv)
    report = build_report(args.split)
    out = EVAL_ROOT / args.split
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"{args.split}: {report['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
