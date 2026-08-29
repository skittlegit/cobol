from __future__ import annotations

import json
from pathlib import Path

import pytest

from cobol_archaeologist.eval.phase5_close import (
    SYSTEM_ORDER,
    build_m5_close,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def analysis() -> dict:
    return build_m5_close()


def test_m5_close_audits_every_frozen_identity_gate(analysis: dict):
    assert analysis["status"] == "COMPLETE"
    assert analysis["milestone"] == "M5_CLOSED"
    assert analysis["issues"] == []
    assert all(analysis["audit_gates"].values())
    assert analysis["benchmark"]["row_count"] == 196
    assert analysis["benchmark"]["canonical_lf_identity_used"] is True
    assert analysis["benchmark"]["excluded_ids_present"] == []
    assert tuple(analysis["systems"]) == SYSTEM_ORDER


def test_every_system_has_required_stratified_and_resource_evidence(analysis: dict):
    expected_classes = {
        "D1_stale_threshold",
        "D2_missing_rule",
        "D3_contradictory",
        "D4_stale_reference_data",
        "D5_boundary_error",
        "D6_dead_code",
        "D7_conformant",
    }
    for system in analysis["systems"].values():
        assert set(system["t1"]) == {"overall", "local", "interprocedural"}
        assert set(system["d1_d7_strata"]) == expected_classes
        assert system["t1"]["overall"]["support"] == 196
        assert "cost_tool_token_evidence" in system


def test_negative_headline_coverage_t6_and_vacated_floor_are_preserved(
    analysis: dict,
):
    headline = analysis["t5.4_headline"]
    assert headline["direction"] == "negative"
    assert headline["bootstrap_95_ci"][1] < 0
    assert headline["paired_randomization_p"] < 0.05
    assert analysis["agent_coverage"]["total_answered"] == 42
    assert analysis["agent_coverage"]["total_abstained"] == 154
    assert analysis["t6"]["pairs"] == 9
    assert analysis["t6"]["reporting_bar_status"] == "NOT_EVALUABLE_FOR_BAR"
    assert analysis["anti_gaming"]["surface_floor"] == "VACATED"
    assert analysis["anti_gaming"]["attacker_result_role"] == (
        "NULL_ANTI_GAMING_EVIDENCE"
    )
    assert set(analysis["anti_gaming"]["weights"]) == {0.0}
    assert analysis["anti_gaming"]["bias"] == 0.0


def test_benchmark_and_detector_claims_are_separated(analysis: dict):
    benchmark = analysis["benchmark_contribution"]
    assert benchmark["establishes"]
    assert any("novelty" in item for item in benchmark["does_not_establish"])
    assert "underperforms" in analysis["detector_finding"]["statement"]
    assert analysis["m4_result_of_record"]["status"] == "NO_GO"
    assert analysis["m5_decision"]["m8_activated"] is False


def test_committed_m5_close_artifacts_match_deterministic_build(analysis: dict):
    output_dir = ROOT / "data" / "eval" / "m5"
    committed_json = json.loads(
        (output_dir / "benchmark-first-analysis.json").read_text("utf-8")
    )
    committed_markdown = (output_dir / "benchmark-first-analysis.md").read_text("utf-8")
    assert committed_json == analysis
    assert committed_markdown == render_markdown(analysis)


def test_t5_5_governance_consumes_amendments_and_preserves_track_b_flag():
    work_order = (ROOT / "docs/tasks/T5.5-work-order.md").read_text("utf-8")
    datasheet = (ROOT / "DATASHEET.md").read_text("utf-8")
    flags = (ROOT / "FLAGS.md").read_text("utf-8")
    status = (ROOT / "STATUS.md").read_text("utf-8")

    assert "blocked on T5.4" not in work_order
    assert "agent-over-attacker floor is **VACATED**" in work_order
    assert "benchmark-first-analysis.{json,md}" in work_order
    assert "significantly underperforms" in datasheet
    assert "NOT_EVALUABLE_FOR_BAR" in datasheet
    assert "Remote T5.5/T5.5A is integrated" in flags
    assert "ACTION NEEDED: re-freeze the split" not in flags
    assert "historical T5.5/T5.5A closed; successor addendum pending" in status
    assert "T5.5 | done for frozen T5.4 benchmark-first analysis" in status
    assert "UI/T7.4 remains deferred" in status
