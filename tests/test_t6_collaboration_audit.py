from __future__ import annotations

import base64
import hashlib

import pytest
from pydantic import ValidationError

from cobol_archaeologist.benchmark.t6_review import (
    CollaborationSubagentAttemptAudit,
)

VALID_FINAL = (
    b'{"decision":"include","drift_type":"D7_conformant","line_level":[],'
    b'"rationale":"Conformant.","uncertainty_notes":null}'
)


def _attempt(**changes: object) -> CollaborationSubagentAttemptAudit:
    prompt = b"Review one item.\nEnvelope: {\"review_item_id\":\"rvw-00000000\"}"
    values: dict[str, object] = {
        "attempt": 1,
        "task_identity": "/root/coordinator/reviewer_01",
        "fork_turns": "none",
        "model_id": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "tools_authorized": 0,
        "prior_item_context_included": False,
        "visible_review_items": 1,
        "staged_source_bundles": 0,
        "envelope_format": "visible_canonical",
        "envelope_separator": "space",
        "prompt_envelope_sha256": hashlib.sha256(
            b'{"review_item_id":"rvw-00000000"}'
        ).hexdigest(),
        "prompt_utf8_base64": base64.b64encode(prompt).decode("ascii"),
        "prompt_utf8_length": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "final_message_utf8_base64": base64.b64encode(VALID_FINAL).decode("ascii"),
        "final_message_utf8_length": len(VALID_FINAL),
        "final_message_sha256": hashlib.sha256(VALID_FINAL).hexdigest(),
        "outcome": "accepted",
    }
    values.update(changes)
    return CollaborationSubagentAttemptAudit.model_validate(values)


def test_collaboration_attempt_binds_exact_prompt_and_final_bytes() -> None:
    attempt = _attempt()

    assert attempt.model_id == "gpt-5.6-luna"
    assert attempt.fork_turns == "none"
    assert attempt.tools_authorized == 0


def test_collaboration_attempt_rejects_a_tampered_byte_hash() -> None:
    with pytest.raises(ValidationError, match="byte length/hash mismatch"):
        _attempt(final_message_sha256="0" * 64)


def test_collaboration_attempt_rejects_valid_json_marked_invalid() -> None:
    with pytest.raises(ValidationError, match="schema-invalid collaboration attempt"):
        _attempt(outcome="schema_invalid")
