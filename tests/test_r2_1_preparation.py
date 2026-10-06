from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_r2_1.py"
spec = importlib.util.spec_from_file_location("r2_prepare", SCRIPT)
assert spec is not None and spec.loader is not None
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


@pytest.mark.parametrize("value", [
    {"labels": {"program_level": "drift"}},
    {"nested": [{"gold_rationale": "mutation answer"}]},
    {"source": {"provenance": {"mutation": "MO-1"}}},
    {"detector_scores": {"correct": True}},
])
def test_visible_review_packets_reject_nested_hidden_metadata(value):
    with pytest.raises(ValueError, match="hidden metadata"):
        prepare.check_visible(value)


def test_actual_source_and_regulation_packet_is_allowed():
    prepare.check_visible({"regulation": {"version": "frozen", "text": "Rule"},
                           "source": "MOVE 100 TO WS-LIMIT", "caveats": ["Not complete compliance"]})


@pytest.mark.parametrize("name", ["CBTRN02C.cbl", "BATCHCT2.cbl"])
def test_unsupported_regulatory_behavior_does_not_get_fake_fixtures(name):
    protocol, caveats = prepare.authored_fixtures({"case_id": "migration_test",
        "primary_program": name, "frozen_sources": [{"path": name, "sha256": "a" * 64}]}, {}, "b" * 64)
    assert all(not fixtures for fixtures in protocol.checks.values())
    assert any("unavailable" in limitation for limitation in caveats)


def test_existing_preparation_bytes_cannot_be_rewritten(tmp_path):
    path = tmp_path / "fixture.json"
    prepare.immutable_bytes(path, b"original")
    with pytest.raises(ValueError, match="refusing to replace"):
        prepare.immutable_bytes(path, b"changed")
