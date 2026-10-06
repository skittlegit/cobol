from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/freeze_r1_7.py"
spec = importlib.util.spec_from_file_location("r17_decision", SCRIPT)
assert spec is not None and spec.loader is not None
decision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decision)


@pytest.mark.parametrize("host,refs,gates,expected", [
    (True, True, {"quality": True}, "GO"),
    (True, True, {"quality": False}, "NO_GO"),
    (True, False, {"quality": True}, "NOT_EVALUABLE"),
    (True, False, {"quality": False}, "NOT_EVALUABLE"),
    (False, True, {"quality": True}, "NOT_EVALUABLE"),
])
def test_validity_precedes_quality(host, refs, gates, expected):
    assert decision.derive_status(host_valid=host, signed_references_valid=refs,
                                  quality_gates=gates) == expected


@pytest.mark.parametrize("gates", [{}, {"quality": "false"}, {"quality": 1}])
def test_unavailable_or_untyped_quality_cannot_pass(gates):
    with pytest.raises(ValueError, match="boolean mapping"):
        decision.derive_status(host_valid=True, signed_references_valid=True,
                               quality_gates=gates)


def test_pinned_input_tampering_and_path_escape_fail_closed(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b"original")
    pin = decision.pin(tmp_path, "input.json")
    decision.verify_pins(tmp_path, [pin])
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        decision.verify_pins(tmp_path, [pin])
    with pytest.raises(ValueError, match="escapes"):
        decision.verify_pins(tmp_path, [{"path": "../outside.json", "sha256": "0" * 64}])


def test_frozen_decision_cannot_be_replaced(tmp_path):
    decision.immutable_write(tmp_path, "decision.json", {"status": "NOT_EVALUABLE"})
    decision.immutable_write(tmp_path, "decision.json", {"status": "NOT_EVALUABLE"})
    with pytest.raises(ValueError, match="refusing to replace"):
        decision.immutable_write(tmp_path, "decision.json", {"status": "GO"})
