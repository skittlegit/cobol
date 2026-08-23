from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cobol_archaeologist.eval.phase5_headline import (
    CANONICAL_TEST_SHA256,
    EXCLUDED_IDS,
    FROZEN_INPUT_PATHS,
    REQUIRED_ERROR_CATEGORIES,
    _lf_sha256,
    build_headline_outputs,
    load_frozen_inputs,
    paired_f1_comparison,
)

ROOT = Path(__file__).resolve().parents[1]


def _hashes() -> dict[str, str]:
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in FROZEN_INPUT_PATHS
    }


def test_canonical_lf_hash_is_line_ending_invariant(tmp_path: Path):
    artifact = tmp_path / "manifest.json"
    artifact.write_bytes(b'{\r\n  "status": "frozen"\r\n}\r\n')

    expected = hashlib.sha256(b'{\n  "status": "frozen"\n}\n').hexdigest()
    assert _lf_sha256(artifact) == expected


def test_frozen_headline_preflight_and_supports_reconcile():
    report, errors = build_headline_outputs(
        bootstrap_resamples=200,
        randomization_samples=500,
    )

    assert report["status"] == "EVALUABLE"
    assert report["issues"] == []
    assert report["benchmark"]["sha256"] == CANONICAL_TEST_SHA256
    assert report["benchmark"]["canonical_lf_identity_used"] is True
    assert report["benchmark"]["row_count"] == 196
    assert report["benchmark"]["excluded_ids_present"] == []
    assert set(report["benchmark"]["excluded_candidate_ids"]) == EXCLUDED_IDS

    identities = report["system_identities"]
    assert set(identities) == {
        "agent",
        "plain_llm",
        "rag_dense",
        "rag_reranker",
        "oracle_slice",
        "train_majority",
        "prevalence_random",
        "static_keyword",
        "attacker_with_bases",
    }
    assert all(row["row_count"] == 196 for row in identities.values())
    assert all(row["instance_ids_match_frozen_order"] for row in identities.values())
    assert all(row["source_identity_matches"] for row in identities.values())

    for metrics in report["metrics"].values():
        assert (
            metrics["locus"]["local"]["support"]
            + metrics["locus"]["interprocedural"]["support"]
            == metrics["overall"]["support"]
            == 196
        )
        assert sum(row["support"] for row in metrics["class_strata"].values()) == 196

    assert REQUIRED_ERROR_CATEGORIES <= set(errors["systems"]["agent"])


def test_headline_build_is_deterministic_and_does_not_mutate_frozen_inputs():
    before = _hashes()
    first = build_headline_outputs(
        bootstrap_resamples=200,
        randomization_samples=500,
    )
    second = build_headline_outputs(
        bootstrap_resamples=200,
        randomization_samples=500,
    )

    assert first == second
    assert _hashes() == before


def test_pairing_fails_closed_when_instance_sets_differ():
    frozen = load_frozen_inputs()
    with pytest.raises(ValueError, match="instance IDs do not align"):
        paired_f1_comparison(
            frozen.structured["agent"],
            frozen.structured["rag_reranker"][:-1],
            locus="interprocedural",
            bootstrap_resamples=20,
            randomization_samples=20,
            seed=1,
        )


def test_frozen_amendments_and_t6_limit_are_preserved():
    report, _ = build_headline_outputs(
        bootstrap_resamples=200,
        randomization_samples=500,
    )

    primary = report["paired_comparisons"]["primary"]
    assert primary["left_system"] == "agent"
    assert primary["right_system"] == "rag_reranker"
    assert primary["locus"] == "interprocedural"
    assert primary["paired_rows"] == 36
    assert "bootstrap_95_ci" in primary
    assert "paired_randomization_p" in primary
    assert primary["effect_size"]["metric"] == "absolute_f1_difference"

    floor = report["frozen_decisions"]["surface_floor"]
    assert floor["status"] == "VACATED"
    assert floor["used_as_pass_fail_gate"] is False
    assert report["headline_result"]["comparator"] == "rag_reranker"

    t6 = report["t6"]
    assert t6["pairs"] == 9
    assert t6["failures"] == 9 - t6["successes"]
    assert t6["reporting_bar_status"] == "NOT_EVALUABLE_FOR_BAR"
    assert t6["reporting_bar_evaluable"] is False


def test_committed_headline_artifacts_have_full_sampling_and_required_schema():
    report = json.loads((ROOT / "data/eval/m5/report.json").read_text("utf-8"))
    errors = json.loads((ROOT / "data/eval/m5/error-analysis.json").read_text("utf-8"))

    assert report["status"] == "EVALUABLE"
    assert report["methodology"]["bootstrap_resamples"] == 10_000
    assert report["methodology"]["randomization_samples"] == 20_000
    assert report["error_analysis_summary"] == errors["summary"]
    assert report["cost_efficiency"]["dollar_cost"] == "not_recorded"
    assert report["frozen_decisions"]["surface_floor"]["status"] == "VACATED"
