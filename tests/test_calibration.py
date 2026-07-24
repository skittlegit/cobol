"""T4.4 coverage, abstention, tier, and confidence gates."""

from __future__ import annotations

from cobol_archaeologist.eval.calibration import calibration
from tests.test_eval_metrics import SPLIT, _record, _rows


def test_all_abstain_reports_zero_coverage_without_fake_confidence():
    records = [_record(row, abstained=True) for row in _rows(SPLIT)[:3]]
    result = calibration(records)

    assert result["coverage"] == 0
    assert result["answered"] == 0
    assert result["brier_score"] is None
    assert result["expected_calibration_error"] is None
    assert result["calibration_bins"] == []


def test_answered_records_report_tiers_and_bin_boundaries():
    records = [_record(row) for row in _rows(SPLIT)[:4]]
    result = calibration(records, bins=10)

    assert result["coverage"] == 1
    assert result["tier_counts"] == {"2": 4}
    assert result["calibration_bins"] == [
        {
            "lower": 0.8,
            "upper": 0.9,
            "n": 4,
            "mean_confidence": 0.85,
            "accuracy": 1.0,
        }
    ]
    assert result["brier_score"] == 0.022500000000000006
