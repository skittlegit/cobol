"""Fail-closed pair-aware correction for the six T6 temporal-flip failures."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    ReviewResponse,
    validate_blinded_review_record,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    BlindedReviewItem,
    artifact_sha256_matches,
    load_blinded_review_packet,
)
from cobol_archaeologist.schemas import RegulationClause

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
CorrectionPairID = Literal[
    "t6v2-candidate-01",
    "t6v2-candidate-02",
    "t6v2-candidate-03",
    "t6v2-candidate-04",
    "t6v2-candidate-05",
    "t6v2-candidate-10",
]
CORRECTION_PAIR_ORDER: tuple[CorrectionPairID, ...] = (
    "t6v2-candidate-01",
    "t6v2-candidate-02",
    "t6v2-candidate-03",
    "t6v2-candidate-04",
    "t6v2-candidate-05",
    "t6v2-candidate-10",
)


class PairCorrectionSideInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Literal["left", "right"]
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    authority: RegulationClause
    source_alias: str = Field(pattern=r"^src-[0-9a-f]{12}$")
    sealed_side_judgment: ReviewResponse


class PairCorrectionPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    correction_pair_id: CorrectionPairID
    correction_call_id: str = Field(pattern=r"^pcall-[0-9a-f]{12}$")
    shared_source_text: str = Field(min_length=20)
    sides: tuple[PairCorrectionSideInput, PairCorrectionSideInput]

    @model_validator(mode="after")
    def _two_distinct_ordered_sides(self) -> PairCorrectionPlanItem:
        if [side.position for side in self.sides] != ["left", "right"]:
            raise ValueError("correction sides must be ordered left then right")
        if len({side.review_item_id for side in self.sides}) != 2:
            raise ValueError("correction pair must contain two distinct sides")
        return self


class PairCorrectionSideResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    review_response: ReviewResponse


class PairCorrectionCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correction_call_id: str = Field(pattern=r"^pcall-[0-9a-f]{12}$")
    sides: tuple[PairCorrectionSideResponse, PairCorrectionSideResponse]

    @model_validator(mode="after")
    def _contains_two_distinct_sides(self) -> PairCorrectionCompletion:
        if len({side.review_item_id for side in self.sides}) != 2:
            raise ValueError("pair correction must return two distinct sides")
        return self


class PairCorrectionAttemptAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: Literal[1]
    task_identity: str = Field(min_length=1)
    fork_turns: Literal["none"]
    model_id: Literal["gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    tools_authorized: Literal[0]
    prior_pair_context_included: Literal[False]
    visible_pairs: Literal[1]
    prompt_utf8_base64: str = Field(min_length=1)
    prompt_utf8_length: int = Field(ge=1)
    prompt_sha256: Sha256
    final_message_utf8_base64: str = Field(min_length=1)
    final_message_utf8_length: int = Field(ge=1)
    final_message_sha256: Sha256
    outcome: Literal["validated_flip", "rejected_nonflip"]

    @model_validator(mode="after")
    def _exact_bytes(self) -> PairCorrectionAttemptAudit:
        try:
            prompt = base64.b64decode(self.prompt_utf8_base64, validate=True)
            final = base64.b64decode(self.final_message_utf8_base64, validate=True)
            prompt.decode("utf-8")
            final.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("pair correction bytes are not canonical UTF-8") from exc
        if (
            len(prompt) != self.prompt_utf8_length
            or hashlib.sha256(prompt).hexdigest() != self.prompt_sha256
            or len(final) != self.final_message_utf8_length
            or hashlib.sha256(final).hexdigest() != self.final_message_sha256
        ):
            raise ValueError("pair correction byte length/hash mismatch")
        PairCorrectionCompletion.model_validate_json(final)
        return self


class PairCorrectionItemAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correction_pair_id: CorrectionPairID
    correction_call_id: str = Field(pattern=r"^pcall-[0-9a-f]{12}$")
    review_item_order: tuple[str, str]
    envelope_sha256: Sha256
    attempt: PairCorrectionAttemptAudit


class PairCorrectionAuditManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    audit_variant: Literal["pair_aware_ai_correction"]
    finalized: Literal[True]
    review_role: Literal["pair_aware_ai_correction"]
    reviewer_pseudonym: str = Field(min_length=1)
    failed_promotion_report: ArtifactPin
    correction_plan: ArtifactPin
    packet: ArtifactPin
    primary_responses: ArtifactPin
    adjudication_responses: ArtifactPin
    responses: ArtifactPin
    provider: Literal["chatgpt-codex-collaboration"]
    model_id: Literal["gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    fork_turns_per_attempt: Literal["none"]
    fresh_task_per_pair: Literal[True]
    visible_pairs_per_call: Literal[1]
    tools_authorized_per_call: Literal[0]
    prior_pair_context_included: Literal[False]
    proposal_labels_visible: Literal[False]
    item_count: Literal[6]
    validated_flip_count: int = Field(ge=0, le=6)
    rejected_nonflip_count: int = Field(ge=0, le=6)
    pair_order: tuple[CorrectionPairID, ...]
    items: list[PairCorrectionItemAudit]

    @model_validator(mode="after")
    def _fixed_scope(self) -> PairCorrectionAuditManifest:
        if self.pair_order != CORRECTION_PAIR_ORDER:
            raise ValueError("pair correction scope/order differs from frozen six pairs")
        if [item.correction_pair_id for item in self.items] != list(self.pair_order):
            raise ValueError("pair correction items differ from frozen order")
        tasks = [item.attempt.task_identity for item in self.items]
        if len(tasks) != len(set(tasks)):
            raise ValueError("pair correction task identities must be unique")
        validated = sum(
            item.attempt.outcome == "validated_flip" for item in self.items
        )
        rejected = sum(
            item.attempt.outcome == "rejected_nonflip" for item in self.items
        )
        if (
            self.validated_flip_count != validated
            or self.rejected_nonflip_count != rejected
            or validated + rejected != 6
        ):
            raise ValueError("pair correction outcome counts differ from one-shot calls")
        return self


class PairCorrectionBridgeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    finalized: Literal[True]
    projection: Literal["pair_correction_to_t6_promotion_v1"]
    correction_audit_manifest: ArtifactPin
    correction_responses: ArtifactPin
    pair_order: tuple[CorrectionPairID, ...]
    pair_members: dict[CorrectionPairID, tuple[str, str]]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_pin(root: Path, pin: ArtifactPin, *, label: str) -> Path:
    path = (root / pin.path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"{label} leaves repository or is missing")
    if not artifact_sha256_matches(path, pin.sha256):
        raise ValueError(f"{label} pin changed")
    return path


def _compact(value: BaseModel | dict[str, object]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def build_pair_correction_prompt(item: PairCorrectionPlanItem) -> str:
    """Return the exact one-pair, proposal-blind Luna/max correction prompt."""

    schema = (
        '{"correction_call_id":"pcall-12hex","sides":['
        '{"review_item_id":"rvw-8hex","review_response":'
        '{"decision":"include|exclude|needs_adjudication","drift_type":"D1_stale_threshold|D2_missing_rule|'
        'D3_contradictory|D4_stale_reference_data|D5_boundary_error|D6_dead_code|'
        'D7_conformant","line_level":[{"program":"nonempty","line":1,'
        '"source_alias":"src-12hex"}],"rationale":"nonempty",'
        '"uncertainty_notes":"string or null"}}]}'
    )
    return (
        "You are the non-human pair_aware_ai_correction reviewer for exactly one "
        "temporal COBOL comparison. Use only the envelope below. Compare its two "
        "authority versions against the shared source and independently judge each "
        "side. The included earlier judgments are advisory and may contain semantic "
        "mistakes. Do not use files, web, tools, prior context, or outside knowledge. "
        "For each side, D7 has no citations and every non-D7 label requires visible "
        "1-based source citations using that side's alias. Return only JSON with this "
        "exact shape: "
        f"{schema}\nEnvelope: "
        + json.dumps(
            pair_correction_envelope(item),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def pair_correction_envelope(item: PairCorrectionPlanItem) -> dict[str, object]:
    """Return the model-visible envelope, excluding the canonical pair mapping."""

    return {
        "correction_call_id": item.correction_call_id,
        "shared_source_text": item.shared_source_text,
        "sides": [
            {
                "position": side.position,
                "review_item_id": side.review_item_id,
                "authority": side.authority.model_dump(mode="json"),
                "source_alias": side.source_alias,
                "sealed_side_judgment": side.sealed_side_judgment.model_dump(
                    mode="json"
                ),
            }
            for side in item.sides
        ],
    }


def _load_blinded_rows(path: Path) -> dict[str, BlindedReviewRecord]:
    return {
        row.review_item_id: row
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
        for row in [BlindedReviewRecord.model_validate_json(raw)]
    }


def require_temporal_flip(completion: PairCorrectionCompletion) -> None:
    """Apply the hidden benchmark invariant after independent model judgment."""

    side_responses = [side.review_response for side in completion.sides]
    if any(result.decision != "include" for result in side_responses) or {
        result.drift_type == "D7_conformant" for result in side_responses
    } != {False, True}:
        raise ValueError("pair correction output does not form a temporal flip")


def validate_pair_correction_audit(
    *, root: Path, manifest_path: Path
) -> PairCorrectionAuditManifest:
    manifest = PairCorrectionAuditManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    plan_path = _check_pin(root, manifest.correction_plan, label="correction plan")
    failure_path = _check_pin(
        root, manifest.failed_promotion_report, label="failed promotion report"
    )
    packet_path = _check_pin(root, manifest.packet, label="correction packet")
    primary_path = _check_pin(
        root, manifest.primary_responses, label="correction primary responses"
    )
    adjudication_path = _check_pin(
        root, manifest.adjudication_responses, label="correction adjudication responses"
    )
    responses_path = _check_pin(
        root, manifest.responses, label="correction responses"
    )
    packet = load_blinded_review_packet(packet_path)
    packet_by_id: dict[str, BlindedReviewItem] = {
        item.review_item_id: item for item in packet
    }
    primary = _load_blinded_rows(primary_path)
    adjudication = _load_blinded_rows(adjudication_path)
    resolved = {**primary, **adjudication}
    plans = [
        PairCorrectionPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    responses = [
        PairCorrectionCompletion.model_validate_json(raw)
        for raw in responses_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    if len(plans) != 6 or len(responses) != 6:
        raise ValueError("pair correction must contain exactly six pairs")
    from cobol_archaeologist.benchmark.t6_review import T6ReviewPromotionReport

    failure = T6ReviewPromotionReport.model_validate_json(
        failure_path.read_text(encoding="utf-8")
    )
    derived_scope = tuple(
        gap.pair_id
        for gap in failure.gaps
        if gap.code == "pair_ineligible" and gap.pair_id is not None
    )
    if failure.evaluation_ready or derived_scope != CORRECTION_PAIR_ORDER:
        raise ValueError("pair correction scope differs from failed promotion evidence")
    all_ids: list[str] = []
    for plan, audit, response in zip(plans, manifest.items, responses, strict=True):
        ids = tuple(side.review_item_id for side in plan.sides)
        all_ids.extend(ids)
        if (
            plan.correction_pair_id != audit.correction_pair_id
            or plan.correction_call_id != audit.correction_call_id
            or response.correction_call_id != plan.correction_call_id
            or ids != audit.review_item_order
            or tuple(side.review_item_id for side in response.sides) != ids
            or audit.envelope_sha256
            != hashlib.sha256(_compact(pair_correction_envelope(plan))).hexdigest()
        ):
            raise ValueError("pair correction order differs from frozen plan")
        for side in plan.sides:
            packet_item = packet_by_id[side.review_item_id]
            if (
                side.authority != packet_item.authority
                or side.source_alias != packet_item.source_alias
                or plan.shared_source_text != packet_item.source_text
                or side.sealed_side_judgment
                != resolved[side.review_item_id].review_response
            ):
                raise ValueError("pair correction plan differs from sealed review input")
        prompt = build_pair_correction_prompt(plan).encode("utf-8")
        final = base64.b64decode(
            audit.attempt.final_message_utf8_base64, validate=True
        )
        if (
            base64.b64decode(audit.attempt.prompt_utf8_base64, validate=True)
            != prompt
            or PairCorrectionCompletion.model_validate_json(final) != response
            or prompt.count(b"Envelope:") != 1
            or prompt.count(_compact(pair_correction_envelope(plan))) != 1
        ):
            raise ValueError("pair correction transcript differs from exact prompt/output")
        try:
            require_temporal_flip(response)
        except ValueError:
            expected_outcome = "rejected_nonflip"
        else:
            expected_outcome = "validated_flip"
        if audit.attempt.outcome != expected_outcome:
            raise ValueError("pair correction outcome differs from hidden flip gate")
        for side in response.sides:
            validate_blinded_review_record(
                record=BlindedReviewRecord(
                    review_item_id=side.review_item_id,
                    reviewer_pseudonym=manifest.reviewer_pseudonym,
                    completed_at="1970-01-01T00:00:00Z",
                    review_response=side.review_response,
                ),
                item=packet_by_id[side.review_item_id],
            )
    if len(all_ids) != 12 or len(set(all_ids)) != 12:
        raise ValueError("pair correction must cover exactly 12 unique sides")
    return manifest


def validate_pair_correction_bridge(
    *, root: Path, bridge_path: Path
) -> tuple[PairCorrectionBridgeManifest, list[BlindedReviewRecord]]:
    bridge = PairCorrectionBridgeManifest.model_validate_json(
        bridge_path.read_text(encoding="utf-8")
    )
    audit_path = _check_pin(
        root, bridge.correction_audit_manifest, label="correction audit"
    )
    audit = validate_pair_correction_audit(root=root, manifest_path=audit_path)
    responses_path = _check_pin(
        root, bridge.correction_responses, label="projected correction responses"
    )
    rows = [
        BlindedReviewRecord.model_validate_json(raw)
        for raw in responses_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    source_path = _check_pin(root, audit.responses, label="raw correction responses")
    completions = [
        PairCorrectionCompletion.model_validate_json(raw)
        for raw in source_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    accepted_pairs = [
        (pair_id, completion)
        for pair_id, completion, item in zip(
            audit.pair_order, completions, audit.items, strict=True
        )
        if item.attempt.outcome == "validated_flip"
    ]
    expected = [
        BlindedReviewRecord(
            review_item_id=side.review_item_id,
            reviewer_pseudonym=audit.reviewer_pseudonym,
            completed_at="1970-01-01T00:00:00Z",
            review_response=side.review_response,
        )
        for _, completion in accepted_pairs
        for side in completion.sides
    ]
    expected_members = {
        pair_id: tuple(
            side.review_item_id for side in completion.sides
        )
        for pair_id, completion in accepted_pairs
    }
    if (
        rows != expected
        or bridge.pair_order != tuple(expected_members)
        or bridge.pair_members != expected_members
    ):
        raise ValueError("pair correction bridge differs from validated audit")
    return bridge, rows
