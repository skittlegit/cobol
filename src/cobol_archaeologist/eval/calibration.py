"""Coverage, abstention, tier, and confidence reporting for T4.4."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from cobol_archaeologist.eval.metrics import detection
from cobol_archaeologist.eval.schemas import EvaluationRecord, TrajectoryAssessment


def _correct(record: EvaluationRecord) -> bool:
    return bool(
        record.prediction
        and record.prediction.drift_type == record.gold.drift_type
    )


def calibration(
    records: Sequence[EvaluationRecord],
    assessments: Sequence[TrajectoryAssessment] = (),
    *,
    bins: int = 10,
) -> dict:
    if bins < 1:
        raise ValueError("bins must be positive")
    available = [record for record in records if not record.infrastructure_error]
    answered = [record for record in available if not record.abstained]
    reason_counts = Counter(
        record.abstention_reason or "unspecified"
        for record in available
        if record.abstained
    )
    budget_exhaustions = sum(
        bool(record.trajectory and record.trajectory.budget_exhausted)
        for record in available
    )
    attempted_unavailable: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    for record in answered:
        if record.verification is None:
            continue
        tier_counts[str(int(record.verification.tier))] += 1
        for attempt in record.verification.tier_attempts:
            if attempt.outcome == "unavailable":
                attempted_unavailable[str(int(attempt.tier))] += 1

    buckets: dict[int, list[EvaluationRecord]] = defaultdict(list)
    for record in answered:
        index = min(int(record.confidence * bins), bins - 1)
        buckets[index].append(record)
    bin_rows = []
    ece = 0.0
    for index in range(bins):
        rows = buckets[index]
        if not rows:
            continue
        mean_confidence = sum(row.confidence for row in rows) / len(rows)
        accuracy = sum(_correct(row) for row in rows) / len(rows)
        weight = len(rows) / len(answered)
        ece += weight * abs(mean_confidence - accuracy)
        bin_rows.append(
            {
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "n": len(rows),
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
            }
        )
    brier = (
        sum((record.confidence - int(_correct(record))) ** 2 for record in answered)
        / len(answered)
        if answered
        else None
    )
    assessment_by_id = {item.instance_id: item for item in assessments}
    per_tier_faithfulness: dict[str, dict] = {}
    for tier, count in sorted(tier_counts.items()):
        tier_rows = [
            record
            for record in answered
            if record.verification is not None
            and str(int(record.verification.tier)) == tier
        ]
        faithful = sum(
            bool(
                (assessment := assessment_by_id.get(record.instance_id))
                and assessment.evidence_path_ok
                and assessment.code_fact_ok
                and assessment.shortcut_free
                and record.prediction.regulation_clause
                == record.gold.regulation_clause
            )
            for record in tier_rows
        )
        per_tier_faithfulness[tier] = {
            "n": count,
            "faithfulness": faithful / count,
        }
    return {
        "full_coverage_detection": detection(records),
        "coverage": len(answered) / len(available) if available else 0.0,
        "answered": len(answered),
        "available": len(available),
        "abstention_reasons": dict(reason_counts),
        "budget_exhaustions": budget_exhaustions,
        "tier_counts": dict(tier_counts),
        "attempted_unavailable": dict(attempted_unavailable),
        "calibration_bins": bin_rows,
        "brier_score": brier,
        "expected_calibration_error": ece if answered else None,
        "per_tier_faithfulness": per_tier_faithfulness,
    }
