"""Provider-free checks for report provenance and measured denominators."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("r17_report", ROOT / "scripts/report_r1_7.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_evidence_manifest_binds_every_rendered_claim():
    out = ROOT / "data/eval/m4"
    manifest = json.loads((out / "report-evidence-manifest.json").read_text(encoding="utf-8"))
    report.verify_pins(ROOT, manifest["inputs"])
    for name, expected in manifest["outputs"].items():
        assert report.sha(out / name) == expected
    for claim in manifest["claims"]:
        document = json.loads((out / claim["report"]).read_text(encoding="utf-8"))
        value = report.pointer(document, claim["json_pointer"])
        actual = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        assert actual == claim["value_sha256"]
        assert claim["report_sha256"] == manifest["outputs"][claim["report"]]
        markdown = (out / claim["report"].replace(".json", ".md")).read_text(encoding="utf-8")
        assert f"`{claim['id']}`" in markdown


def test_modified_source_evidence_is_rejected(tmp_path):
    source = tmp_path / "observation.json"
    source.write_bytes(b'{"observation":"original"}')
    original = report.sha(source)
    source.write_bytes(b'{"observation":"rewritten"}')
    with pytest.raises(ValueError, match="Evidence changed"):
        report.verify_pins(tmp_path, {"observation.json": original})


def test_report_keeps_host_and_signed_validity_distinct():
    document = json.loads((ROOT / "data/eval/m4/report.json").read_text(encoding="utf-8"))
    assert document["terminal_evidence"]["host_status"] == "VALID"
    assert document["signed_reference_discrepancies"]["full_entries"] == 2
    assert document["signed_reference_discrepancies"]["temporal_entries"] == 2
    assert document["temporal"]["pairs"] == 20
    assert document["temporal"]["successes"] == 7
    assert document["quality_gates"]["temporal_paired_accuracy"] is False
    assert "detector_decision" not in document
    for system in document["systems"].values():
        assert system["record_count"] == 196
        assert sum(c["rows"] for c in system["class_stratum_cells"]) == 196
        assert system["faithfulness_status"] == "not_recorded_no_independent_assessments"


def test_profile_counts_host_observations_without_zero_filling_provider_usage():
    document = json.loads((ROOT / "data/eval/m4/performance-profile.json").read_text(encoding="utf-8"))
    assert set(document["resource_telemetry"].values()) == {"not_recorded"}
    inputs = report.Inputs(ROOT)
    for system, cells in document["systems"].items():
        rows = inputs.records(report.LINEAGE / "full" / system / f"{system}.jsonl")
        assert report.operation_profile(rows) == cells
        assert cells["overall"]["rows"] == 196
        assert cells["overall"]["tool_calls"] == (
            cells["overall"]["successful_observations"] + cells["overall"]["error_observations"])
        assert cells["local"]["rows"] + cells["interprocedural"]["rows"] == 196
