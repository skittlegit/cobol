"""The project site's data is exported from the report, never hand-edited."""

from __future__ import annotations

import importlib.util
import json
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


def _export(tmp_path, report) -> dict:
    return json.loads(_site().build(tmp_path / "site.json", report).read_text(encoding="utf-8"))


def test_site_data_carries_exactly_the_report_values(tmp_path):
    from cobol_archaeologist.eval.report import gate_rows

    report = _evaluated_report()
    results = _export(tmp_path, report)["results"]

    assert results["decision"] == "NO_GO"
    shown = [(g["name"], g["measured"], g["required"], g["pass"]) for g in results["gates"]]
    assert shown == list(gate_rows(report))
    assert results["passed"] == 6
    assert results["comparison"]["delta"] == 0.1234
    assert results["temporal"]["successes"] == 15


def test_pending_data_states_what_is_outstanding(tmp_path):
    report = {
        "decision": "NOT_EVALUABLE",
        "reason": "required rows are missing",
        "missing_or_failed": {"detector": ["a"] * 145, "temporal": ["b"] * 44},
    }
    data = _export(tmp_path, report)

    assert data["results"] == {
        "decision": "NOT_EVALUABLE",
        "status": "145 required rows have no result yet.",
    }
    assert data["history"][-1]["decision"] == "NOT_EVALUABLE"
    assert data["benchmark"]["splits"][2]["name"] == "test"


def test_web_app_types_match_the_exported_keys():
    # The app reads site.json through web/src/types.ts; a renamed key must
    # fail here rather than render as blank on the site.
    types = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")
    for key in ("excavation", "benchmark", "results", "history", "classes",
                "comparison", "per_class", "confusion", "localisation", "tiers",
                "temporal", "per_pair", "measured", "required"):
        assert f"{key}:" in types or f"{key}?:" in types, key
