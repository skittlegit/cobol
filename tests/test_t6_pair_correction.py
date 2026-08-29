"""Fail-closed tests for the six-pair T6 correction protocol."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.benchmark.t6_pair_correction import (
    CORRECTION_PAIR_ORDER,
    PairCorrectionAttemptAudit,
    PairCorrectionCompletion,
    PairCorrectionPlanItem,
    PairCorrectionSideResponse,
    build_pair_correction_prompt,
    pair_correction_envelope,
    require_temporal_flip,
    validate_pair_correction_audit,
    validate_pair_correction_bridge,
)

ROOT = Path(__file__).resolve().parents[1]
CORRECTION_DIR = ROOT / "data/benchmark/t6-v2/review/pair-correction-v2"


def _plans() -> list[PairCorrectionPlanItem]:
    return [
        PairCorrectionPlanItem.model_validate_json(raw)
        for raw in (CORRECTION_DIR / "correction-plan.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if raw.strip()
    ]


def _completion(*, left_d7: bool, right_d7: bool) -> PairCorrectionCompletion:
    plan = _plans()[0]
    responses = []
    for side, is_d7 in zip(plan.sides, (left_d7, right_d7), strict=True):
        response = side.sealed_side_judgment.model_copy(deep=True)
        if is_d7:
            response = response.model_copy(
                update={
                    "decision": "include",
                    "drift_type": "D7_conformant",
                    "line_level": [],
                }
            )
        elif response.drift_type == "D7_conformant":
            response = response.model_copy(
                update={
                    "decision": "include",
                    "drift_type": "D2_missing_rule",
                    "line_level": [
                        {
                            "program": "CORRECTION",
                            "line": 1,
                            "source_alias": side.source_alias,
                        }
                    ],
                }
            )
        responses.append(
            PairCorrectionSideResponse(
                review_item_id=side.review_item_id,
                review_response=response,
            )
        )
    return PairCorrectionCompletion(
        correction_call_id=plan.correction_call_id,
        sides=tuple(responses),
    )


def test_frozen_plan_has_exact_six_pair_scope_and_unique_opaque_calls() -> None:
    plans = _plans()
    assert tuple(plan.correction_pair_id for plan in plans) == CORRECTION_PAIR_ORDER
    assert len({plan.correction_call_id for plan in plans}) == 6
    assert len(
        {side.review_item_id for plan in plans for side in plan.sides}
    ) == 12


def test_model_visible_prompts_hide_coordinator_and_outcome_state() -> None:
    forbidden = (
        "t6v2-candidate",
        "pair_proposals",
        "data/benchmark",
        "proposal",
        "gold",
        "temporal flip",
        "exactly one included d7",
        "one d7 and one",
    )
    for plan in _plans():
        prompt = build_pair_correction_prompt(plan)
        lowered = prompt.lower()
        assert all(token not in lowered for token in forbidden)
        assert prompt.count("Envelope:") == 1
        assert plan.correction_call_id in prompt
        assert plan.correction_pair_id not in prompt


def test_prompt_files_are_exact_deterministic_builder_bytes() -> None:
    manifest = json.loads(
        (CORRECTION_DIR / "prompt-manifest.coordinator-private.json").read_text(
            encoding="utf-8"
        )
    )
    for plan, call in zip(_plans(), manifest["calls"], strict=True):
        prompt = build_pair_correction_prompt(plan).encode("utf-8")
        path = ROOT / call["prompt"]["path"]
        assert path.read_bytes() == prompt
        assert len(prompt) == call["prompt_utf8_length"]
        assert hashlib.sha256(prompt).hexdigest() == call["prompt"]["sha256"]


def test_envelope_contains_only_opaque_call_and_review_ids() -> None:
    plan = _plans()[0]
    envelope = pair_correction_envelope(plan)
    encoded = json.dumps(envelope, sort_keys=True).lower()
    assert plan.correction_call_id in encoded
    assert plan.correction_pair_id not in encoded
    assert "correction_pair_id" not in encoded
    assert "candidate_side_id" not in encoded


def test_temporal_flip_accepts_exactly_one_d7() -> None:
    require_temporal_flip(_completion(left_d7=True, right_d7=False))
    require_temporal_flip(_completion(left_d7=False, right_d7=True))


@pytest.mark.parametrize("left_d7,right_d7", [(True, True), (False, False)])
def test_temporal_flip_rejects_nonflipping_results(
    left_d7: bool, right_d7: bool
) -> None:
    with pytest.raises(ValueError, match="does not form a temporal flip"):
        require_temporal_flip(_completion(left_d7=left_d7, right_d7=right_d7))


def test_temporal_flip_rejects_noninclude_decision() -> None:
    completion = _completion(left_d7=True, right_d7=False)
    bad = completion.model_copy(deep=True)
    bad.sides[1].review_response.decision = "needs_adjudication"
    with pytest.raises(ValueError, match="does not form a temporal flip"):
        require_temporal_flip(bad)


def test_completion_rejects_duplicate_or_extra_sides() -> None:
    completion = _completion(left_d7=True, right_d7=False)
    payload = completion.model_dump(mode="json")
    payload["sides"] = [payload["sides"][0], payload["sides"][0]]
    with pytest.raises(ValidationError, match="two distinct sides"):
        PairCorrectionCompletion.model_validate(payload)
    payload = completion.model_dump(mode="json")
    payload["sides"].append(payload["sides"][0])
    with pytest.raises(ValidationError):
        PairCorrectionCompletion.model_validate(payload)


def test_attempt_audit_pins_exact_prompt_and_final_bytes() -> None:
    plan = _plans()[0]
    prompt = build_pair_correction_prompt(plan).encode("utf-8")
    final = _completion(left_d7=True, right_d7=False).model_dump_json().encode(
        "utf-8"
    )
    common = {
        "attempt": 1,
        "task_identity": "/root/coordinator/pair-correction-01",
        "fork_turns": "none",
        "model_id": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "tools_authorized": 0,
        "prior_pair_context_included": False,
        "visible_pairs": 1,
        "prompt_utf8_base64": base64.b64encode(prompt).decode("ascii"),
        "prompt_utf8_length": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "final_message_utf8_base64": base64.b64encode(final).decode("ascii"),
        "final_message_utf8_length": len(final),
        "final_message_sha256": hashlib.sha256(final).hexdigest(),
        "outcome": "validated_flip",
    }
    PairCorrectionAttemptAudit.model_validate(common)
    with pytest.raises(ValidationError, match="byte length/hash mismatch"):
        PairCorrectionAttemptAudit.model_validate(
            {**common, "final_message_sha256": "0" * 64}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt", 2),
        ("fork_turns", "all"),
        ("model_id", "gpt-5.6-sol"),
        ("reasoning_effort", "high"),
        ("tools_authorized", 1),
        ("prior_pair_context_included", True),
        ("visible_pairs", 2),
        ("outcome", "retry"),
    ],
)
def test_attempt_audit_rejects_protocol_drift(field: str, value: object) -> None:
    plan = _plans()[0]
    prompt = build_pair_correction_prompt(plan).encode("utf-8")
    final = _completion(left_d7=True, right_d7=False).model_dump_json().encode(
        "utf-8"
    )
    payload = {
        "attempt": 1,
        "task_identity": "pair-01",
        "fork_turns": "none",
        "model_id": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "tools_authorized": 0,
        "prior_pair_context_included": False,
        "visible_pairs": 1,
        "prompt_utf8_base64": base64.b64encode(prompt).decode("ascii"),
        "prompt_utf8_length": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "final_message_utf8_base64": base64.b64encode(final).decode("ascii"),
        "final_message_utf8_length": len(final),
        "final_message_sha256": hashlib.sha256(final).hexdigest(),
        "outcome": "validated_flip",
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        PairCorrectionAttemptAudit.model_validate(payload)


def test_sealed_six_call_diagnostic_replays_as_six_rejections() -> None:
    evidence = (
        ROOT
        / "data/benchmark/t6-v2/review/evidence/pair-aware-ai-correction"
    )
    audit = validate_pair_correction_audit(
        root=ROOT, manifest_path=evidence / "audit-manifest.json"
    )
    bridge, projected = validate_pair_correction_bridge(
        root=ROOT, bridge_path=evidence / "promotion-bridge-manifest.json"
    )
    assert audit.validated_flip_count == 0
    assert audit.rejected_nonflip_count == 6
    assert [item.attempt.outcome for item in audit.items] == [
        "rejected_nonflip"
    ] * 6
    assert bridge.pair_order == ()
    assert bridge.pair_members == {}
    assert projected == []
