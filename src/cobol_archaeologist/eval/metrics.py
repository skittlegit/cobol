"""Frozen T1-T6 metric implementation."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence

from cobol_archaeologist.eval.schemas import EvaluationRecord, TrajectoryAssessment
from cobol_archaeologist.eval.statistics import exact_binomial_interval

DRIFT_TYPES = (
    "D1_stale_threshold",
    "D2_missing_rule",
    "D3_contradictory",
    "D4_stale_reference_data",
    "D5_boundary_error",
    "D6_dead_code",
    "D7_conformant",
)


def _answered(record: EvaluationRecord) -> bool:
    return not record.infrastructure_error and not record.abstained


def _is_drift(instance) -> bool:
    return instance.drift_type != "D7_conformant"


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def detection(records: Sequence[EvaluationRecord]) -> dict:
    tp = fp = fn = tn = 0
    answered = 0
    correct_answered = 0
    for record in records:
        if record.infrastructure_error:
            continue
        gold_positive = _is_drift(record.gold)
        if record.abstained:
            if gold_positive:
                fn += 1
            continue
        answered += 1
        predicted_positive = _is_drift(record.prediction)
        if gold_positive and predicted_positive:
            tp += 1
        elif not gold_positive and predicted_positive:
            fp += 1
        elif gold_positive:
            fn += 1
        else:
            tn += 1
        correct_answered += gold_positive == predicted_positive
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": _safe_div(2 * precision * recall, precision + recall),
        "answer_rate": _safe_div(answered, sum(not r.infrastructure_error for r in records)),
        "answered_accuracy": _safe_div(correct_answered, answered),
    }


def classification(records: Sequence[EvaluationRecord]) -> dict:
    per_class: dict[str, dict] = {}
    for drift_type in DRIFT_TYPES:
        tp = fp = fn = 0
        for record in records:
            if record.infrastructure_error:
                continue
            gold_match = record.gold.drift_type == drift_type
            predicted_match = _answered(record) and record.prediction.drift_type == drift_type
            tp += int(gold_match and predicted_match)
            fp += int(not gold_match and predicted_match)
            fn += int(gold_match and not predicted_match)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        per_class[drift_type] = {
            "precision": precision,
            "recall": recall,
            "f1": _safe_div(2 * precision * recall, precision + recall),
            "support": sum(r.gold.drift_type == drift_type for r in records),
        }
    return {
        "macro_f1": sum(row["f1"] for row in per_class.values()) / len(DRIFT_TYPES),
        "per_class": per_class,
    }


def _programs(instance) -> list[str]:
    return list(dict.fromkeys(locus.program for locus in instance.code_locus.loci))


def _paragraphs(instance) -> list[tuple[str, str | None]]:
    return list(
        dict.fromkeys(
            (locus.program, locus.paragraph) for locus in instance.code_locus.loci
        )
    )


def _lines(instance) -> list[tuple[str, str | None, int]]:
    return [
        (line.program, line.file, line.line) for line in instance.labels.line_level
    ]


def localization(records: Sequence[EvaluationRecord]) -> dict:
    eligible = [record for record in records if _is_drift(record.gold)]
    answered = [
        record
        for record in eligible
        if _answered(record) and _is_drift(record.prediction)
    ]

    def at_k(gold_values, predicted_values, k: int) -> float:
        return float(bool(set(gold_values) & set(predicted_values[:k])))

    dimensions = {
        "program": _programs,
        "paragraph": _paragraphs,
        "line": _lines,
    }
    result: dict[str, dict] = {}
    for name, accessor in dimensions.items():
        result[name] = {}
        for k in (1, 3):
            hits = sum(
                at_k(accessor(record.gold), accessor(record.prediction), k)
                for record in answered
            )
            result[name][f"accuracy@{k}"] = _safe_div(hits, len(eligible))
    overlaps = []
    for record in answered:
        gold = set(_lines(record.gold))
        predicted = set(_lines(record.prediction))
        if gold:
            overlaps.append(len(gold & predicted) / len(gold | predicted))
    result["line"]["overlap"] = _safe_div(sum(overlaps), len(eligible))
    return result


def faithfulness(
    records: Sequence[EvaluationRecord],
    assessments: Iterable[TrajectoryAssessment],
) -> dict:
    assessment_by_id = {item.instance_id: item for item in assessments}
    tiers: dict[str, list[bool]] = defaultdict(list)
    for record in records:
        if not _answered(record) or record.verification is None:
            continue
        assessment = assessment_by_id.get(record.instance_id)
        citation = (
            record.prediction.regulation_clause.doc,
            record.prediction.regulation_clause.clause_id,
            record.prediction.regulation_clause.version,
            record.prediction.regulation_clause.effective_date,
        ) == (
            record.gold.regulation_clause.doc,
            record.gold.regulation_clause.clause_id,
            record.gold.regulation_clause.version,
            record.gold.regulation_clause.effective_date,
        )
        code_fact = bool(
            assessment
            and assessment.code_fact_ok
            and assessment.evidence_path_ok
            and assessment.shortcut_free
        )
        tiers[str(int(record.verification.tier))].append(citation and code_fact)
    per_tier = {
        tier: {"faithfulness": _safe_div(sum(values), len(values)), "n": len(values)}
        for tier, values in sorted(tiers.items())
    }
    return {
        "per_tier": per_tier,
        "aggregate": {
            "faithfulness": _safe_div(
                sum(sum(values) for values in tiers.values()),
                sum(len(values) for values in tiers.values()),
            ),
            "n": sum(len(values) for values in tiers.values()),
        },
    }


def versioned_judgment(records: Sequence[EvaluationRecord]) -> dict:
    groups: dict[str, list[EvaluationRecord]] = defaultdict(list)
    for record in records:
        key = json.dumps(
            record.gold.code_locus.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        groups[key].append(record)
    pairs = []
    for rows in groups.values():
        versions = {
            (
                row.gold.regulation_clause.version,
                row.gold.regulation_clause.effective_date,
            )
            for row in rows
        }
        verdicts = {_is_drift(row.gold) for row in rows}
        if len(rows) == 2 and len(versions) == 2 and len(verdicts) == 2:
            pairs.append(rows)
    successes = 0
    for pair in pairs:
        successes += int(
            all(
                _answered(row)
                and _is_drift(row.prediction) == _is_drift(row.gold)
                for row in pair
            )
        )
    interval = (
        exact_binomial_interval(successes, len(pairs)) if pairs else (None, None)
    )
    return {
        "pairs": len(pairs),
        "successes": successes,
        "paired_accuracy": _safe_div(successes, len(pairs)),
        "exact_95_ci": interval,
        "reporting_bar_evaluable": len(pairs) >= 20,
        "reporting_bar_met": len(pairs) >= 20
        and _safe_div(successes, len(pairs)) >= 0.70,
    }


def evaluate(
    records: Sequence[EvaluationRecord],
    assessments: Sequence[TrajectoryAssessment] = (),
) -> dict:
    ids = [record.instance_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate evaluation instance IDs")
    strata = {
        "local": [r for r in records if not r.gold.code_locus.is_interprocedural],
        "interprocedural": [
            r for r in records if r.gold.code_locus.is_interprocedural
        ],
    }
    return {
        "overall": {
            "t1_detection": detection(records),
            "t2_localization": localization(records),
            "t3_classification": classification(records),
            "t4_faithfulness": faithfulness(records, assessments),
            "t6_versioned_judgment": versioned_judgment(records),
        },
        "strata": {
            name: {
                "t1_detection": detection(rows),
                "t2_localization": localization(rows),
                "t3_classification": classification(rows),
            }
            for name, rows in strata.items()
        },
    }
