"""The project site is generated from the report, never hand-edited."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _site():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evaluated_report() -> dict:
    keys = [
        "t1_f1",
        "balanced_accuracy",
        "answer_rate",
        "answered_accuracy",
        "interprocedural_advantage",
        "temporal_paired_accuracy",
        "zero_unverified_findings",
    ]
    classes = ["D1_stale_threshold", "D7_conformant", "ABSTAIN"]
    return {
        "decision": "NO_GO",
        "split": "test",
        "detector": {
            "t1": {
                "f1": 0.7312,
                "balanced_accuracy": 0.6123,
                "answer_rate": 0.8456,
                "answered_accuracy": 0.9011,
            },
            "confusion": {c: {p: 1 for p in classes} for c in classes[:2]},
        },
        "interprocedural_comparison": {
            "delta_f1": 0.1234,
            "bootstrap_95_ci": [0.0111, 0.2222],
            "paired_randomization_p": 0.0123,
            "paired_rows": 60,
        },
        "temporal": {
            "successes": 15,
            "pairs": 22,
            "paired_accuracy": 15 / 22,
            "exact_95_ci": [0.45, 0.86],
            "per_pair": {f"pair-{i:02d}": i <= 15 for i in range(1, 23)},
        },
        "gate_results": {key: key != "balanced_accuracy" for key in keys},
    }


def test_results_page_shows_exactly_the_report_values(tmp_path):
    site = _site()
    from cobol_archaeologist.eval.report import gate_rows

    report = _evaluated_report()
    page = site.build(tmp_path / "site", report).read_text(encoding="utf-8")

    assert "NO-GO" in page
    for name, measured, required, _ in gate_rows(report):
        assert site.E(measured) in page, name
        assert site.E(required) in page, name
    assert page.count("<td class=fail>") == 1


def test_pending_page_states_what_is_outstanding(tmp_path):
    site = _site()
    report = {
        "decision": "NOT_EVALUABLE",
        "reason": "required rows are missing",
        "missing_or_failed": {"detector": ["a"] * 145, "temporal": ["b"] * 44},
        "gates": {
            "t1_f1": 0.7,
            "balanced_accuracy": 0.65,
            "answer_rate": 0.6,
            "answered_accuracy": 0.8,
            "interprocedural_delta_f1": 0.1,
            "interprocedural_p": 0.05,
            "temporal_paired_accuracy": 0.7,
            "temporal_min_pairs": 20,
        },
    }
    page = site.build(tmp_path / "site", report).read_text(encoding="utf-8")

    assert "Pending" in page
    assert "145 required rows have no result yet." in page
    assert "held-out test rows" in page
