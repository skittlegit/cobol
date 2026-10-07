import pytest

from scripts.report_r2_stage_migration import summarize


def record(case, outcome, status):
    return {
        "validation": {
            "case_id": case,
            "outcome": outcome,
            "capability": "batch_executable",
            "checks": [{"check_id": "compile", "status": status}],
            "affected_line_precision": None,
            "changed_line_count": 0,
            "unrelated_change_count": 0,
        }
    }


def test_failed_and_unavailable_checks_keep_full_denominator():
    cases = [
        {"case_id": x, "drift_type": "D1", "stratum": "local"} for x in ("a", "b", "c")
    ]
    result = summarize(
        [
            record("a", "pass", "pass"),
            record("b", "fail", "unavailable"),
            record("c", "abstention", "not_applicable"),
        ],
        cases,
    )
    assert result["checks"]["compile"]["denominator"] == 3
    assert result["checks"]["compile"]["pass_rate"] == 1 / 3
    assert result["patch_rate"]["value"] == 2 / 3
    assert result["outcomes"] == {"pass": 1, "fail": 1, "abstention": 1}
    assert result["provider_usage"] == "not_recorded"


def test_inactive_track_has_null_rates():
    result = summarize([], [])
    assert result["pass_rate"] == {"numerator": 0, "denominator": 0, "value": None}


def test_pending_or_wrong_case_cannot_reconcile():
    with pytest.raises(ValueError, match="pending"):
        summarize([], [{"case_id": "a"}])
    with pytest.raises(ValueError, match="case order"):
        summarize([record("b", "pass", "pass")], [{"case_id": "a"}])
