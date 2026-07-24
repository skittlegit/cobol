"""T4.2 hand-computed metric and statistics gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from cobol_archaeologist.agent.trajectory import Trajectory
from cobol_archaeologist.eval.metrics import evaluate, versioned_judgment
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.eval.statistics import (
    exact_binomial_interval,
    paired_bootstrap_delta,
    paired_randomization_p,
)
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "benchmark" / "v1-pre" / "test.jsonl"
SEED = ROOT / "data" / "benchmark" / "seed" / "real_curated.jsonl"
GOLDEN = ROOT / "tests" / "fixtures" / "agent" / "golden_late_fee_trajectory.json"


def _rows(path: Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _record(
    gold: DriftInstance,
    *,
    prediction: DriftInstance | None = None,
    abstained: bool = False,
) -> EvaluationRecord:
    golden = Trajectory.model_validate_json(GOLDEN.read_text(encoding="utf-8"))
    if abstained:
        return EvaluationRecord(
            instance_id=gold.instance_id,
            gold=gold,
            prediction=None,
            abstained=True,
            abstention_reason="insufficient evidence",
            system_id="fixture",
            source_sha256="0" * 64,
            run_key=f"fixture:{gold.instance_id}",
        )
    prediction = prediction or gold
    trajectory = golden.model_copy(
        update={
            "finding": prediction,
            "verification": golden.verification,
            "abstained": False,
            "abstention_reason": None,
        }
    )
    return EvaluationRecord(
        instance_id=gold.instance_id,
        gold=gold,
        prediction=prediction,
        confidence=0.85,
        verification=trajectory.verification,
        trajectory=trajectory,
        abstained=False,
        system_id="fixture",
        source_sha256="0" * 64,
        run_key=f"fixture:{gold.instance_id}",
    )


def test_perfect_seven_class_predictions_score_one():
    rows = _rows(SPLIT)
    gold = [next(row for row in rows if row.drift_type == kind) for kind in {
        row.drift_type for row in rows
    }]
    result = evaluate([_record(row) for row in gold])

    assert len(gold) == 7
    assert result["overall"]["t1_detection"]["f1"] == 1
    assert result["overall"]["t3_classification"]["macro_f1"] == 1
    assert result["overall"]["t2_localization"]["program"]["accuracy@1"] == 1
    assert result["overall"]["t2_localization"]["line"]["overlap"] == 1


def test_abstention_is_recall_miss_not_false_positive():
    positive = next(row for row in _rows(SPLIT) if row.drift_type != "D7_conformant")
    negative = next(row for row in _rows(SPLIT) if row.drift_type == "D7_conformant")
    result = evaluate([_record(positive, abstained=True), _record(negative)])
    detection = result["overall"]["t1_detection"]

    assert detection["tp"] == 0
    assert detection["fn"] == 1
    assert detection["fp"] == 0
    assert detection["answer_rate"] == 0.5


def test_t6_pairs_use_byte_equivalent_locus_and_exact_interval():
    records = [_record(row) for row in _rows(SEED)]
    result = versioned_judgment(records)

    assert result["pairs"] == 20
    assert result["successes"] == 20
    assert result["paired_accuracy"] == 1
    assert result["reporting_bar_evaluable"] is True
    assert result["exact_95_ci"][0] == pytest.approx(0.832, abs=0.002)
    assert result["exact_95_ci"][1] == 1


def test_metrics_are_order_invariant_and_duplicate_ids_rejected():
    rows = _rows(SPLIT)[:8]
    forward = [_record(row) for row in rows]
    assert evaluate(forward) == evaluate(list(reversed(forward)))
    with pytest.raises(ValueError, match="duplicate"):
        evaluate([forward[0], forward[0]])


def test_statistical_helpers_are_paired_and_deterministic():
    left = [1.0, 1.0, 0.0, 1.0]
    right = [0.0, 1.0, 0.0, 0.0]
    metric = lambda values: sum(values) / len(values)

    first = paired_bootstrap_delta(left, right, metric, resamples=500, seed=7)
    assert first == paired_bootstrap_delta(left, right, metric, resamples=500, seed=7)
    assert first[0] == 0.5
    assert 0 <= paired_randomization_p(
        [True, True, False, True],
        [False, True, False, False],
        samples=500,
        seed=7,
    ) <= 1
    assert exact_binomial_interval(0, 5)[0] == 0
    assert exact_binomial_interval(5, 5)[1] == 1
