"""Fail-closed ingestion and promotion gate for blinded T6-v2 reviews.

The proposal key is deliberately opened only after two complete, distinct
controlled-model review passes have been validated against the frozen blind
packet. The primary is explicitly AI/Sol and the verifier is AI/Luna; neither
pass may be represented as human review.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    BlindedReviewItem,
    CandidatePairProposal,
    CandidateSideProposal,
    PrimaryReviewIdentityProtocol,
    SequentialReleasePolicy,
    T6V2Manifest,
    load_blinded_review_packet,
    load_candidate_pair_proposals,
    load_t6_v2_manifest,
    validate_t6_v2,
)
from cobol_archaeologist.schemas import (
    CodeLocus,
    DriftInstance,
    DriftType,
    Labels,
    Provenance,
    SourceLineRef,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ReviewRole = Literal["ai_primary", "independent_verifier", "adjudicator"]
ReviewDecision = Literal["include", "exclude", "needs_adjudication"]
AuthorityTarget = Literal[
    "grievance_response_deadline",
    "partnership_beneficial_owner_threshold",
    "central_kyc_update_deadline",
]


class ReviewLineRef(BaseModel):
    """Reviewer citation, preserving the JSON schema's non-empty program rule."""

    model_config = ConfigDict(extra="forbid")

    program: str = Field(min_length=1)
    line: int = Field(ge=1)
    source_alias: str = Field(pattern=r"^src-[0-9a-f]{12}$")


class ReviewResponse(BaseModel):
    """Strict response payload matching ``review/response.schema.json``."""

    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    drift_type: DriftType | None
    line_level: list[ReviewLineRef]
    rationale: str = Field(min_length=1)
    uncertainty_notes: str | None

    @model_validator(mode="after")
    def _decision_and_labels_are_well_formed(self) -> ReviewResponse:
        if self.decision == "exclude":
            if self.drift_type is not None or self.line_level:
                raise ValueError(
                    "excluded items must have null drift_type and no citations"
                )
            return self
        if self.drift_type is None:
            if self.decision == "include":
                raise ValueError("included items require a drift_type")
            if self.line_level:
                raise ValueError("an unresolved null drift_type cannot cite lines")
            return self
        if self.drift_type == "D7_conformant" and self.line_level:
            raise ValueError("D7 responses must have empty line citations")
        if self.drift_type != "D7_conformant" and not self.line_level:
            raise ValueError("non-D7 responses require at least one line citation")
        return self


def build_controlled_review_prompt(
    item: BlindedReviewItem,
    *,
    attempt: int,
    review_role: Literal["ai_primary", "independent_verifier"],
) -> str:
    """Canonical one-envelope prompt replayed by either controlled-model gate."""

    visible = {
        "review_item_id": item.review_item_id,
        "authority": item.authority.model_dump(mode="json"),
        "source_alias": item.source_alias,
        "source_text": item.source_text,
    }
    return (
        f"You are the {review_role} reviewer for exactly one blinded COBOL/authority "
        "judgment. Use only the single envelope below. You have no access to pair "
        "membership, proposals, canonical paths, other items, prior responses, or "
        "tools. Localize any non-conformity directly in the visible source. Return "
        "only JSON matching the supplied schema. D7 requires no line citations; "
        "every non-D7 label requires at least one {program,line,source_alias} "
        "citation. Do not infer or discuss a temporal partner.\n"
        f"Fresh isolated attempt: {attempt}\n"
        f"Envelope: {json.dumps(visible, ensure_ascii=False, separators=(',', ':'))}"
    )


def build_independent_review_prompt(item: BlindedReviewItem, *, attempt: int) -> str:
    """Backward-compatible canonical prompt for the Luna verifier."""

    return build_controlled_review_prompt(
        item, attempt=attempt, review_role="independent_verifier"
    )


class BlindedReviewRecord(BaseModel):
    """One returned JSONL row, with no proposal or pair identifiers."""

    model_config = ConfigDict(extra="forbid")

    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    reviewer_pseudonym: str = Field(min_length=1)
    completed_at: AwareDatetime
    review_response: ReviewResponse

    @field_validator("completed_at", mode="before")
    @classmethod
    def _completed_at_is_json_datetime_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise TypeError("completed_at must be a date-time string")
        return value


class ReviewArtifactMetadata(BaseModel):
    """Separately stored role binding for one blinded response artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    review_role: ReviewRole
    reviewer_pseudonym: str = Field(min_length=1)
    packet: ArtifactPin
    release_policy: ArtifactPin
    responses: ArtifactPin
    sequential_delivery_audit: ArtifactPin
    controlled_model_audit_manifest: ArtifactPin | None
    expected_item_count: int = Field(ge=0)
    delivery_mode: Literal["sequential_one_item"]
    full_packet_distributed: Literal[False]
    canonical_source_map_distributed: Literal[False]
    prior_item_context_retained: Literal[False]

    @model_validator(mode="after")
    def _role_specific_evidence(self) -> ReviewArtifactMetadata:
        model_role = self.review_role in {"ai_primary", "independent_verifier"}
        if model_role != (self.controlled_model_audit_manifest is not None):
            raise ValueError(
                "controlled model roles require an audit manifest and adjudication forbids one"
            )
        return self


class PinnedReviewMetadata(ArtifactPin):
    """Hash pin for a role-metadata artifact."""


class ReviewEvidencePins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_primary: PinnedReviewMetadata
    independent_verifier: PinnedReviewMetadata
    adjudication: PinnedReviewMetadata | None = None
    ai_adjudication_bridge_manifest: ArtifactPin | None = None
    pair_correction_bridge_manifest: ArtifactPin | None = None
    replacement_bridge_manifest: ArtifactPin | None = None


class SequentialDeliveryAuditEntry(BaseModel):
    """One immutable completed-delivery event in exact release order."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    source_envelope_sha256: Sha256
    response_sha256: Sha256
    previous_entry_sha256: Sha256 | None


class IndependentReviewRequestIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    review_role: Literal["ai_primary", "independent_verifier"]
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    release_ordinal: int = Field(ge=1, le=22)
    attempt: int = Field(ge=1)
    source_alias: str = Field(pattern=r"^src-[0-9a-f]{12}$")
    source_text_sha256: Sha256
    authority_sha256: Sha256
    packet: ArtifactPin
    release_policy: ArtifactPin
    provider: Literal["chatgpt-codex"]
    authentication: Literal["ChatGPT"]
    authentication_identity_sha256: Sha256
    model_id: Literal["gpt-5.6-sol", "gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    transport: Literal["wsl", "native"]
    codex_binary: str = Field(min_length=1)
    prompt_sha256: Sha256
    schema_sha256: Sha256
    runtime_source_sha256: Sha256
    expected_request_sha256: Sha256
    visible_review_items: Literal[1]
    staged_source_bundles: Literal[0]
    tools_authorized: Literal[0]
    prior_item_context_included: Literal[False]


class IndependentAttemptAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    request_identity: ArtifactPin
    raw_execution: ArtifactPin
    raw_completion_marker: ArtifactPin
    expected_request_sha256: Sha256
    outcome: Literal["schema_invalid", "accepted"]
    invalid_marker: ArtifactPin | None

    @model_validator(mode="after")
    def _marker_matches_outcome(self) -> IndependentAttemptAudit:
        if (self.outcome == "schema_invalid") != (self.invalid_marker is not None):
            raise ValueError(
                "invalid_marker must occur exactly on schema-invalid attempts"
            )
        return self


class IndependentItemAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    attempts: list[IndependentAttemptAudit] = Field(min_length=1)

    @model_validator(mode="after")
    def _retry_chain_is_contiguous(self) -> IndependentItemAudit:
        if [item.attempt for item in self.attempts] != list(
            range(1, len(self.attempts) + 1)
        ):
            raise ValueError("attempt chain must be contiguous from one")
        if self.attempts[-1].outcome != "accepted" or any(
            item.outcome != "schema_invalid" for item in self.attempts[:-1]
        ):
            raise ValueError("retry chain must end in exactly one accepted attempt")
        return self


class IndependentVerifierAuditManifest(BaseModel):
    """Aggregate evidence for one isolated controlled-model review pass."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    finalized: Literal[True]
    review_role: Literal["ai_primary", "independent_verifier"]
    reviewer_pseudonym: str = Field(min_length=1)
    packet: ArtifactPin
    release_policy: ArtifactPin
    responses: ArtifactPin
    sequential_delivery_audit: ArtifactPin
    provider: Literal["chatgpt-codex"]
    authentication: Literal["ChatGPT"]
    authentication_identity_sha256: Sha256
    model_id: Literal["gpt-5.6-sol", "gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    visible_review_items_per_call: Literal[1]
    staged_source_bundles_per_call: Literal[0]
    tools_authorized_per_call: Literal[0]
    prior_item_context_included: Literal[False]
    item_count: Literal[22]
    release_ordinal_order: list[int]
    review_item_order: list[str]
    items: list[IndependentItemAudit]

    @model_validator(mode="after")
    def _complete_order(self) -> IndependentVerifierAuditManifest:
        expected_model = (
            "gpt-5.6-sol" if self.review_role == "ai_primary" else "gpt-5.6-luna"
        )
        if self.model_id != expected_model:
            raise ValueError("controlled review role uses the wrong frozen model")
        if self.release_ordinal_order != list(range(1, 23)):
            raise ValueError("verifier audit must cover release ordinals 1..22")
        if len(self.review_item_order) != 22 or len(set(self.review_item_order)) != 22:
            raise ValueError("verifier audit must contain 22 unique review items")
        if [item.release_ordinal for item in self.items] != self.release_ordinal_order:
            raise ValueError("verifier audit items differ from ordinal order")
        if [item.review_item_id for item in self.items] != self.review_item_order:
            raise ValueError("verifier audit items differ from review-item order")
        return self


class CollaborationSubagentResponseRecord(BaseModel):
    """Exact accepted model response from an isolated collaboration child."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    audit_variant: Literal["collaboration_subagent"]
    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    task_identity: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    review_response: ReviewResponse


class CollaborationSubagentAttemptAudit(BaseModel):
    """Verbatim prompt/completion evidence without a fabricated native bundle."""

    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    task_identity: str = Field(min_length=1)
    fork_turns: Literal["none"]
    model_id: Literal["gpt-5.6-sol", "gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    tools_authorized: Literal[0]
    prior_item_context_included: Literal[False]
    visible_review_items: Literal[1]
    staged_source_bundles: Literal[0]
    envelope_format: Literal["visible_canonical", "full_blind_packet_row"]
    envelope_separator: Literal["space", "lf"]
    prompt_envelope_sha256: Sha256
    prompt_utf8_base64: str = Field(min_length=1)
    prompt_utf8_length: int = Field(ge=1)
    prompt_sha256: Sha256
    final_message_utf8_base64: str = Field(min_length=1)
    final_message_utf8_length: int = Field(ge=1)
    final_message_sha256: Sha256
    outcome: Literal["schema_invalid", "accepted"]

    @staticmethod
    def _decode_utf8(value: str, *, label: str) -> bytes:
        try:
            raw = base64.b64decode(value, validate=True)
            raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"{label} is not canonical base64-encoded UTF-8") from exc
        return raw

    @model_validator(mode="after")
    def _verbatim_bytes_are_bound(self) -> CollaborationSubagentAttemptAudit:
        prompt = self._decode_utf8(self.prompt_utf8_base64, label="prompt")
        final = self._decode_utf8(
            self.final_message_utf8_base64, label="final message"
        )
        if (
            len(prompt) != self.prompt_utf8_length
            or hashlib.sha256(prompt).hexdigest() != self.prompt_sha256
            or len(final) != self.final_message_utf8_length
            or hashlib.sha256(final).hexdigest() != self.final_message_sha256
        ):
            raise ValueError("collaboration attempt byte length/hash mismatch")
        try:
            ReviewResponse.model_validate_json(final)
        except ValueError:
            if self.outcome != "schema_invalid":
                raise ValueError("accepted collaboration completion is schema-invalid")
        else:
            if self.outcome != "accepted":
                raise ValueError("schema-invalid collaboration attempt is valid")
        return self


class CollaborationSubagentItemAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    source_alias: str = Field(pattern=r"^src-[0-9a-f]{12}$")
    source_envelope_sha256: Sha256
    attempts: list[CollaborationSubagentAttemptAudit] = Field(min_length=1)

    @model_validator(mode="after")
    def _attempt_chain_is_complete(self) -> CollaborationSubagentItemAudit:
        if [item.attempt for item in self.attempts] != list(
            range(1, len(self.attempts) + 1)
        ):
            raise ValueError("attempt chain must be contiguous from one")
        if self.attempts[-1].outcome != "accepted" or any(
            item.outcome != "schema_invalid" for item in self.attempts[:-1]
        ):
            raise ValueError("attempt chain must end in exactly one accepted attempt")
        return self


class CollaborationSubagentAuditManifest(BaseModel):
    """Honest audit for in-product fresh-task model collaboration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    audit_variant: Literal["collaboration_subagent"]
    finalized: Literal[True]
    review_role: Literal["ai_primary", "independent_verifier"]
    reviewer_pseudonym: str = Field(min_length=1)
    packet: ArtifactPin
    release_policy: ArtifactPin
    response_schema: ArtifactPin
    responses: ArtifactPin
    sequential_delivery_audit: ArtifactPin
    provider: Literal["chatgpt-codex-collaboration"]
    model_id: Literal["gpt-5.6-sol", "gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    fork_turns_per_attempt: Literal["none"]
    fresh_task_per_attempt: Literal[True]
    visible_review_items_per_call: Literal[1]
    staged_source_bundles_per_call: Literal[0]
    tools_authorized_per_call: Literal[0]
    prior_item_context_included: Literal[False]
    native_execution_bundle_claimed: Literal[False]
    item_count: Literal[22]
    accepted_count: int = Field(ge=0)
    schema_invalid_attempt_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    release_ordinal_order: list[int]
    review_item_order: list[str]
    items: list[CollaborationSubagentItemAudit]

    @model_validator(mode="after")
    def _complete_collaboration_order(self) -> CollaborationSubagentAuditManifest:
        expected_model = (
            "gpt-5.6-sol" if self.review_role == "ai_primary" else "gpt-5.6-luna"
        )
        if self.model_id != expected_model:
            raise ValueError("collaboration review role uses the wrong frozen model")
        if self.release_ordinal_order != list(range(1, 23)):
            raise ValueError("collaboration audit must cover release ordinals 1..22")
        if len(self.review_item_order) != 22 or len(set(self.review_item_order)) != 22:
            raise ValueError("collaboration audit must contain 22 unique review items")
        if [item.release_ordinal for item in self.items] != self.release_ordinal_order:
            raise ValueError("collaboration audit items differ from ordinal order")
        if [item.review_item_id for item in self.items] != self.review_item_order:
            raise ValueError("collaboration audit items differ from review-item order")
        invalid_count = sum(
            attempt.outcome == "schema_invalid"
            for item in self.items
            for attempt in item.attempts
        )
        if (
            self.accepted_count != len(self.items)
            or self.schema_invalid_attempt_count != invalid_count
            or self.retry_count != invalid_count
        ):
            raise ValueError("collaboration audit summary counts differ from attempts")
        return self


class ExternalPrimaryReviewVerification(BaseModel):
    """Quarantined legacy v1 human evidence; never accepted for T6-v2 AI-primary."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    review_role: Literal["human_primary"]
    reviewer_pseudonym: str = Field(min_length=1)
    primary_review_metadata: ArtifactPin
    sequential_delivery_audit: ArtifactPin
    primary_identity_protocol: ArtifactPin
    identity_verified: Literal[True]
    sequential_delivery_verified: Literal[True]
    verified_by_external_party: str = Field(min_length=1)
    verification_method: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    verified_at: AwareDatetime
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str = Field(min_length=88, max_length=88)

    @field_validator("verified_at", mode="before")
    @classmethod
    def _verified_at_is_json_datetime_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise TypeError("verified_at must be a date-time string")
        return value

    @model_validator(mode="after")
    def _verification_is_external(self) -> ExternalPrimaryReviewVerification:
        if self.verified_by_external_party == self.reviewer_pseudonym:
            raise ValueError("human-primary reviewer cannot verify their own identity")
        return self


class PromotionReviewEvidencePins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_primary_metadata: ArtifactPin
    ai_primary_responses: ArtifactPin
    ai_primary_audit_manifest: ArtifactPin
    independent_verifier_metadata: ArtifactPin
    independent_verifier_responses: ArtifactPin
    adjudication_metadata: ArtifactPin | None
    adjudication_responses: ArtifactPin | None
    ai_adjudication_audit_manifest: ArtifactPin | None
    ai_adjudication_bridge_manifest: ArtifactPin | None
    independent_verifier_audit_manifest: ArtifactPin
    pair_correction_audit_manifest: ArtifactPin | None = None
    pair_correction_bridge_manifest: ArtifactPin | None = None
    pair_correction_responses: ArtifactPin | None = None
    replacement_audit_manifest: ArtifactPin | None = None
    replacement_bridge_manifest: ArtifactPin | None = None
    replacement_plan: ArtifactPin | None = None
    replacement_responses: ArtifactPin | None = None


class FinalizedReviewEvidencePins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_primary_metadata: ArtifactPin
    ai_primary_responses: ArtifactPin
    ai_primary_audit_manifest: ArtifactPin
    independent_verifier_metadata: ArtifactPin
    independent_verifier_responses: ArtifactPin
    adjudication_metadata: ArtifactPin
    adjudication_responses: ArtifactPin
    ai_adjudication_audit_manifest: ArtifactPin | None
    ai_adjudication_bridge_manifest: ArtifactPin | None
    independent_verifier_audit_manifest: ArtifactPin
    pair_correction_audit_manifest: ArtifactPin | None = None
    pair_correction_bridge_manifest: ArtifactPin | None = None
    pair_correction_responses: ArtifactPin | None = None
    replacement_audit_manifest: ArtifactPin | None = None
    replacement_bridge_manifest: ArtifactPin | None = None
    replacement_plan: ArtifactPin | None = None
    replacement_responses: ArtifactPin | None = None


class PromotionGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "excluded",
        "unresolved",
        "proposal_mismatch",
        "pair_ineligible",
        "adjudication_evidence_missing",
    ]
    review_item_id: str | None = None
    pair_id: str | None = None
    detail: str = Field(min_length=1)


class T6ReviewPromotionReport(BaseModel):
    """Pure promotion proposal; writing canonical artifacts is caller-owned."""

    model_config = ConfigDict(extra="forbid")

    evaluation_ready: bool
    target_pair_count: Literal[20]
    evaluation_eligible_pair_count: int = Field(ge=9, le=20)
    carried_pair_count: Literal[9]
    candidate_pair_count: Literal[11]
    review_item_count: Literal[22]
    resolved_candidate_pairs: int = Field(ge=0, le=11)
    gaps: list[PromotionGap]
    proposed_pair_order: list[str]
    proposed_candidate_instance_ids: list[str]
    proposed_instance_order: list[str]
    proposed_pair_members: dict[str, list[str]]
    proposed_authority_targets: dict[str, AuthorityTarget]
    proposed_source_inputs: dict[str, ArtifactPin]
    preparation_manifest: ArtifactPin
    review_evidence: PromotionReviewEvidencePins
    carried_instances: list[DriftInstance]
    candidate_instances: list[DriftInstance]
    controlled_ai_primary_verified: bool
    canonical_artifacts_written: Literal[False] = False

    @model_validator(mode="after")
    def _promotion_is_all_or_nothing(self) -> T6ReviewPromotionReport:
        if set(self.proposed_source_inputs) != set(self.proposed_instance_order):
            raise ValueError("proposed_source_inputs must cover all 40 ordered rows")
        _validate_pair_members(
            pair_order=self.proposed_pair_order,
            instance_order=self.proposed_instance_order,
            pair_members=self.proposed_pair_members,
        )
        if set(self.proposed_authority_targets) != set(self.proposed_pair_order):
            raise ValueError("authority targets must exactly cover all temporal pairs")
        if self.evaluation_ready:
            if not self.controlled_ai_primary_verified:
                raise ValueError(
                    "ready promotion requires the controlled AI-primary audit"
                )
            if self.gaps or len(self.candidate_instances) != 22:
                raise ValueError("ready promotion requires all 22 candidate sides")
            if self.evaluation_eligible_pair_count != 20:
                raise ValueError("ready promotion requires all 20 pairs")
            _validate_temporal_pair_rows(
                rows=[*self.carried_instances, *self.candidate_instances],
                pair_order=self.proposed_pair_order,
                pair_members=self.proposed_pair_members,
                authority_targets=self.proposed_authority_targets,
                source_inputs=self.proposed_source_inputs,
            )
        elif self.candidate_instances:
            raise ValueError("candidate rows cannot be constructed for a failed gate")
        return self


class T6FinalizedManifestProposal(BaseModel):
    """Config-3-compatible manifest proposal, with no filesystem side effect."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    finalized: Literal[True]
    evaluation_ready: Literal[True]
    evaluation_rows: ArtifactPin
    preparation_manifest: ArtifactPin
    promotion_report: ArtifactPin
    review_evidence: FinalizedReviewEvidencePins
    controlled_ai_primary_verified: Literal[True]
    target_pair_count: Literal[20]
    evaluation_side_count: Literal[40]
    pair_order: list[str]
    instance_order: list[str]
    pair_members: dict[str, list[str]]
    authority_targets: dict[str, AuthorityTarget]
    source_inputs: dict[str, ArtifactPin]

    @model_validator(mode="after")
    def _orders_are_complete_and_unique(self) -> T6FinalizedManifestProposal:
        if len(self.pair_order) != 20 or len(set(self.pair_order)) != 20:
            raise ValueError("finalized manifest requires 20 unique ordered pairs")
        if len(self.instance_order) != 40 or len(set(self.instance_order)) != 40:
            raise ValueError("finalized manifest requires 40 unique ordered instances")
        if set(self.source_inputs) != set(self.instance_order):
            raise ValueError("source_inputs must exactly cover finalized instances")
        _validate_pair_members(
            pair_order=self.pair_order,
            instance_order=self.instance_order,
            pair_members=self.pair_members,
        )
        if set(self.authority_targets) != set(self.pair_order):
            raise ValueError("authority targets must exactly cover pair_order")
        return self


class _ValidatedReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    packet: list[BlindedReviewItem]
    primary: dict[str, BlindedReviewRecord]
    verifier: dict[str, BlindedReviewRecord]
    adjudication: dict[str, BlindedReviewRecord]
    pins: PromotionReviewEvidencePins
    controlled_ai_primary_verified: bool
    correction_pair_members: dict[str, tuple[str, str]] = Field(default_factory=dict)
    replacement_pairs: list[tuple[object, object]] = Field(default_factory=list)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_matches(path: Path, expected: str) -> bool:
    """Match frozen text pins across Git's LF/CRLF checkout normalization."""

    data = path.read_bytes()
    candidates = {hashlib.sha256(data).hexdigest()}
    if path.suffix.lower() in {".cbl", ".cpy", ".json", ".jsonl", ".md", ".txt"}:
        lf_data = data.replace(b"\r\n", b"\n")
        candidates.add(hashlib.sha256(lf_data).hexdigest())
        candidates.add(
            hashlib.sha256(lf_data.replace(b"\n", b"\r\n")).hexdigest()
        )
    return expected in candidates


def _repo_path(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"artifact path escapes repository root: {relative}")
    return resolved


def _canonical_bytes(value: BaseModel | dict[str, object]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def external_primary_verification_signing_payload(
    verification: ExternalPrimaryReviewVerification | dict[str, object],
) -> bytes:
    """Return the domain-separated bytes an external verifier must sign."""

    payload = (
        verification.model_dump(mode="json", exclude={"signature_base64"})
        if isinstance(verification, ExternalPrimaryReviewVerification)
        else {
            key: value
            for key, value in verification.items()
            if key != "signature_base64"
        }
    )
    return b"cobol-archaeologist/t6-primary-review/v1\x00" + _canonical_bytes(payload)


def _load_identity_protocol(
    *, root: Path, pin: ArtifactPin
) -> PrimaryReviewIdentityProtocol:
    path = _repo_path(root, pin.path)
    if not path.is_file() or not _hash_matches(path, pin.sha256):
        raise ValueError("primary identity protocol pin changed")
    protocol = PrimaryReviewIdentityProtocol.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    try:
        public_key = base64.b64decode(protocol.public_key_base64, validate=True)
    except ValueError as exc:
        raise ValueError("primary identity protocol public key is not base64") from exc
    if (
        len(public_key) != 32
        or hashlib.sha256(public_key).hexdigest() != protocol.public_key_sha256
    ):
        raise ValueError("primary identity protocol public key pin changed")
    return protocol


def _load_delivery_audit(
    *, root: Path, metadata: ReviewArtifactMetadata
) -> list[SequentialDeliveryAuditEntry]:
    path = _repo_path(root, metadata.sequential_delivery_audit.path)
    if not path.is_file() or not _hash_matches(
        path, metadata.sequential_delivery_audit.sha256
    ):
        raise ValueError("sequential delivery audit pin changed")
    rows = [
        SequentialDeliveryAuditEntry.model_validate_json(raw)
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    if len(rows) != metadata.expected_item_count:
        raise ValueError("delivery audit count differs from review metadata")
    previous: str | None = None
    for row in rows:
        if row.previous_entry_sha256 != previous:
            raise ValueError("delivery audit hash chain is broken")
        previous = hashlib.sha256(_canonical_bytes(row)).hexdigest()
    return rows


def _check_pin(root: Path, pin: ArtifactPin, *, label: str) -> Path:
    path = _repo_path(root, pin.path)
    if not path.is_file() or not _hash_matches(path, pin.sha256):
        raise ValueError(f"{label} pin changed: {pin.path}")
    return path


def _controlled_source_responses(
    *, root: Path, metadata: ReviewArtifactMetadata
) -> ArtifactPin:
    """Return the raw model-response pin behind a validated promotion projection."""

    pin = metadata.controlled_model_audit_manifest
    if pin is None:
        raise ValueError("controlled model audit manifest is required")
    path = _check_pin(root, pin, label="controlled model audit manifest")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("audit_variant") == "collaboration_subagent":
        return CollaborationSubagentAuditManifest.model_validate(raw).responses
    return metadata.responses


def _collaboration_bytes(value: str) -> bytes:
    """Decode byte-exact collaboration evidence already checked by its model."""

    return base64.b64decode(value, validate=True)


def validate_collaboration_subagent_audit(
    *, root: Path, manifest_path: Path
) -> CollaborationSubagentAuditManifest:
    """Validate an honest collaboration audit without claiming native bundles."""

    manifest = CollaborationSubagentAuditManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    packet_path = _check_pin(root, manifest.packet, label="collaboration packet")
    _check_pin(
        root, manifest.release_policy, label="collaboration release policy"
    )
    _check_pin(root, manifest.response_schema, label="collaboration response schema")
    responses_path = _check_pin(
        root, manifest.responses, label="collaboration responses"
    )
    delivery_path = _check_pin(
        root,
        manifest.sequential_delivery_audit,
        label="collaboration sequential audit",
    )
    packet_lines = [
        raw
        for raw in packet_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    packet = load_blinded_review_packet(packet_path)
    responses = [
        CollaborationSubagentResponseRecord.model_validate_json(raw)
        for raw in responses_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    delivery = [
        SequentialDeliveryAuditEntry.model_validate_json(raw)
        for raw in delivery_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    if len(packet) != 22 or len(responses) != 22 or len(delivery) != 22:
        raise ValueError("collaboration evidence must contain exactly 22 items")
    tasks: set[str] = set()
    previous: str | None = None
    for item, packet_line, response, item_audit, delivery_row in zip(
        packet, packet_lines, responses, manifest.items, delivery, strict=True
    ):
        visible = {
            "review_item_id": item.review_item_id,
            "authority": item.authority.model_dump(mode="json"),
            "source_alias": item.source_alias,
            "source_text": item.source_text,
        }
        envelope = json.dumps(
            visible, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        accepted_attempt = item_audit.attempts[-1]
        accepted_envelope = (
            envelope
            if accepted_attempt.envelope_format == "visible_canonical"
            else packet_line.encode("utf-8")
        )
        envelope_sha256 = hashlib.sha256(accepted_envelope).hexdigest()
        final = _collaboration_bytes(accepted_attempt.final_message_utf8_base64)
        parsed = ReviewResponse.model_validate_json(final)
        if (
            response.release_ordinal != item.release_ordinal
            or response.review_item_id != item.review_item_id
            or response.task_identity != accepted_attempt.task_identity
            or response.attempt != accepted_attempt.attempt
            or response.review_response != parsed
            or item_audit.review_item_id != item.review_item_id
            or item_audit.source_alias != item.source_alias
            or item_audit.source_envelope_sha256 != envelope_sha256
            or delivery_row.release_ordinal != item.release_ordinal
            or delivery_row.review_item_id != item.review_item_id
            or delivery_row.source_envelope_sha256 != envelope_sha256
            or delivery_row.response_sha256 != accepted_attempt.final_message_sha256
            or delivery_row.previous_entry_sha256 != previous
        ):
            raise ValueError("collaboration item evidence differs from frozen order")
        validate_blinded_review_record(
            record=BlindedReviewRecord(
                review_item_id=item.review_item_id,
                reviewer_pseudonym=manifest.reviewer_pseudonym,
                completed_at="1970-01-01T00:00:00Z",
                review_response=parsed,
            ),
            item=item,
        )
        for attempt in item_audit.attempts:
            if attempt.model_id != manifest.model_id:
                raise ValueError("collaboration attempt model differs from manifest")
            if attempt.task_identity in tasks:
                raise ValueError("collaboration task identities must be unique")
            tasks.add(attempt.task_identity)
            prompt = _collaboration_bytes(attempt.prompt_utf8_base64)
            attempt_envelope = (
                envelope
                if attempt.envelope_format == "visible_canonical"
                else packet_line.encode("utf-8")
            )
            separator = b" " if attempt.envelope_separator == "space" else b"\n"
            marker = b"Envelope:" + separator + attempt_envelope
            if (
                attempt.prompt_envelope_sha256
                != hashlib.sha256(attempt_envelope).hexdigest()
                or prompt.count(b"Envelope:") != 1
                or prompt.count(marker) != 1
            ):
                raise ValueError("collaboration prompt is not exactly one-item visible")
        previous = hashlib.sha256(_canonical_bytes(delivery_row)).hexdigest()
    return manifest


def _validate_controlled_model_audit(
    *,
    root: Path,
    pin: ArtifactPin,
    metadata: ReviewArtifactMetadata,
    rows: dict[str, BlindedReviewRecord],
    packet: list[BlindedReviewItem],
    expected_role: Literal["ai_primary", "independent_verifier"],
) -> None:
    path = _check_pin(root, pin, label=f"{expected_role} audit manifest")
    raw_audit = json.loads(path.read_text(encoding="utf-8"))
    if raw_audit.get("audit_variant") == "collaboration_subagent":
        audit = validate_collaboration_subagent_audit(
            root=root, manifest_path=path
        )
        expected_order = [
            item.review_item_id
            for item in sorted(packet, key=lambda item: item.release_ordinal)
        ]
        if (
            audit.review_role != expected_role
            or audit.reviewer_pseudonym != metadata.reviewer_pseudonym
            or audit.packet != metadata.packet
            or audit.release_policy != metadata.release_policy
            or audit.review_item_order != expected_order
        ):
            raise ValueError(f"{expected_role} audit differs from review evidence")
        accepted = {
            response.review_item_id: response.review_response
            for response in (
                CollaborationSubagentResponseRecord.model_validate_json(raw)
                for raw in _check_pin(
                    root,
                    audit.responses,
                    label=f"{expected_role} collaboration responses",
                )
                .read_text(encoding="utf-8")
                .splitlines()
                if raw.strip()
            )
        }
        if accepted != {
            item_id: record.review_response for item_id, record in rows.items()
        }:
            raise ValueError(
                f"{expected_role} collaboration audit differs from response JSONL"
            )
        return
    audit = IndependentVerifierAuditManifest.model_validate_json(
        json.dumps(raw_audit)
    )
    expected_order = [
        item.review_item_id
        for item in sorted(packet, key=lambda item: item.release_ordinal)
    ]
    if (
        audit.review_role != expected_role
        or audit.reviewer_pseudonym != metadata.reviewer_pseudonym
        or audit.packet != metadata.packet
        or audit.release_policy != metadata.release_policy
        or audit.responses != metadata.responses
        or audit.sequential_delivery_audit != metadata.sequential_delivery_audit
        or audit.review_item_order != expected_order
    ):
        raise ValueError(f"{expected_role} audit differs from review evidence")
    packet_by_id = {item.review_item_id: item for item in packet}
    for item_audit in audit.items:
        item = packet_by_id[item_audit.review_item_id]
        for attempt in item_audit.attempts:
            identity_path = _check_pin(
                root,
                attempt.request_identity,
                label=f"{expected_role} request identity",
            )
            identity = IndependentReviewRequestIdentity.model_validate_json(
                identity_path.read_text(encoding="utf-8")
            )
            prompt = build_controlled_review_prompt(
                item, attempt=attempt.attempt, review_role=expected_role
            )
            from cobol_archaeologist.eval.codex_batch import strict_codex_schema
            from cobol_archaeologist.eval.config3_live import (
                expected_codex_request_sha256,
            )

            schema = strict_codex_schema(ReviewResponse)
            recomputed_request_sha256 = expected_codex_request_sha256(
                prompt=prompt,
                schema=schema,
                sources={},
                transport=identity.transport,
                codex_binary=identity.codex_binary,
                runtime_source_sha256=identity.runtime_source_sha256,
                chatgpt_account_sha256=audit.authentication_identity_sha256,
                authorized_hunts=(),
            )
            if (
                identity.review_item_id != item.review_item_id
                or identity.review_role != expected_role
                or identity.release_ordinal != item.release_ordinal
                or identity.attempt != attempt.attempt
                or identity.source_alias != item.source_alias
                or identity.source_text_sha256
                != hashlib.sha256(item.source_text.encode("utf-8")).hexdigest()
                or identity.authority_sha256
                != hashlib.sha256(_canonical_bytes(item.authority)).hexdigest()
                or identity.prompt_sha256
                != hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                or identity.schema_sha256
                != hashlib.sha256(_canonical_bytes(schema)).hexdigest()
                or identity.packet != audit.packet
                or identity.release_policy != audit.release_policy
                or identity.authentication_identity_sha256
                != audit.authentication_identity_sha256
                or identity.model_id != audit.model_id
                or identity.expected_request_sha256 != attempt.expected_request_sha256
                or identity.expected_request_sha256 != recomputed_request_sha256
            ):
                raise ValueError(
                    f"{expected_role} request identity differs from frozen item"
                )
            execution_path = _check_pin(
                root, attempt.raw_execution, label="verifier raw execution"
            )
            marker_path = _check_pin(
                root, attempt.raw_completion_marker, label="verifier raw marker"
            )
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if (
                execution.get("request_sha256") != attempt.expected_request_sha256
                or execution.get("tool_logs") != []
                or marker.get("key") != attempt.expected_request_sha256
                or marker.get("request_sha256") != attempt.expected_request_sha256
            ):
                raise ValueError("verifier raw bundle differs from request identity")
            if attempt.invalid_marker is not None:
                _check_pin(root, attempt.invalid_marker, label="invalid-attempt marker")
                try:
                    ReviewResponse.model_validate_json(execution["final_message"])
                except ValueError:
                    pass
                else:
                    raise ValueError("schema-invalid attempt contains a valid response")
            else:
                accepted = ReviewResponse.model_validate_json(
                    execution["final_message"]
                )
                if accepted != rows[item.review_item_id].review_response:
                    raise ValueError(
                        "accepted verifier bundle differs from response JSONL"
                    )


def _validate_pair_members(
    *,
    pair_order: list[str],
    instance_order: list[str],
    pair_members: dict[str, list[str]],
) -> None:
    if set(pair_members) != set(pair_order):
        raise ValueError("pair_members keys must exactly match pair_order")
    flattened: list[str] = []
    for pair_id in pair_order:
        members = pair_members[pair_id]
        if len(members) != 2 or len(set(members)) != 2:
            raise ValueError(f"{pair_id} must contain exactly two distinct instances")
        flattened.extend(members)
    if flattened != instance_order or len(set(flattened)) != 40:
        raise ValueError(
            "pair_members must cover all 40 instances once in frozen order"
        )


def _authority_target(row: DriftInstance) -> AuthorityTarget:
    clause = row.regulation_clause
    haystack = f"{clause.doc} {clause.clause_id} {clause.text}".lower()
    if "complain" in haystack or "ombudsman" in haystack:
        return "grievance_response_deadline"
    if "beneficial owner" in haystack or "partnership" in haystack:
        return "partnership_beneficial_owner_threshold"
    if (
        "registry" in haystack
        or "central kyc" in haystack
        or "ckycr" in haystack
        or ("kyc" in haystack and "upload" in haystack)
    ):
        return "central_kyc_update_deadline"
    raise ValueError(f"unrecognized T6 authority target for {row.instance_id}")


def _validate_temporal_pair_rows(
    *,
    rows: list[DriftInstance],
    pair_order: list[str],
    pair_members: dict[str, list[str]],
    authority_targets: dict[str, AuthorityTarget],
    source_inputs: dict[str, ArtifactPin],
) -> None:
    if len(rows) != 40:
        raise ValueError("temporal promotion requires exactly 40 rows")
    rows_by_id = {row.instance_id: row for row in rows}
    if len(rows_by_id) != 40 or set(rows_by_id) != set(source_inputs):
        raise ValueError("all 40 temporal rows must occur exactly once")
    for pair_id in pair_order:
        left, right = (rows_by_id[item] for item in pair_members[pair_id])
        if left.regulation_clause.version == right.regulation_clause.version:
            raise ValueError(f"{pair_id} must span distinct regulation versions")
        if (
            left.regulation_clause.effective_date
            == right.regulation_clause.effective_date
        ):
            raise ValueError(f"{pair_id} must span distinct effective dates")
        if left.code_locus != right.code_locus:
            raise ValueError(f"{pair_id} sides must share an identical code locus")
        if source_inputs[left.instance_id] != source_inputs[right.instance_id]:
            raise ValueError(f"{pair_id} sides must share one pinned source")
        if {
            left.drift_type == "D7_conformant",
            right.drift_type == "D7_conformant",
        } != {
            False,
            True,
        }:
            raise ValueError(f"{pair_id} must contain one D7 and one drift side")
        actual_targets = {_authority_target(left), _authority_target(right)}
        if actual_targets != {authority_targets[pair_id]}:
            raise ValueError(f"{pair_id} sides must share one authority target")


def _load_pinned_metadata(
    *, root: Path, pin: PinnedReviewMetadata
) -> ReviewArtifactMetadata:
    path = _repo_path(root, pin.path)
    if not path.is_file() or not _hash_matches(path, pin.sha256):
        raise ValueError(f"review metadata pin changed: {pin.path}")
    return ReviewArtifactMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def _load_external_verification(
    *,
    root: Path,
    pin: ArtifactPin,
    primary_metadata_pin: ArtifactPin,
    primary_meta: ReviewArtifactMetadata,
    identity_protocol_pin: ArtifactPin,
) -> ExternalPrimaryReviewVerification:
    path = _repo_path(root, pin.path)
    if not path.is_file() or not _hash_matches(path, pin.sha256):
        raise ValueError("external human-primary verification pin changed")
    verification = ExternalPrimaryReviewVerification.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if verification.reviewer_pseudonym != primary_meta.reviewer_pseudonym:
        raise ValueError("external verification names a different primary reviewer")
    if (
        verification.primary_review_metadata.path != primary_metadata_pin.path
        or verification.primary_review_metadata.sha256 != primary_metadata_pin.sha256
    ):
        raise ValueError("external verification pins different primary metadata")
    if verification.sequential_delivery_audit != primary_meta.sequential_delivery_audit:
        raise ValueError("external verification pins a different delivery audit")
    if verification.primary_identity_protocol != identity_protocol_pin:
        raise ValueError("external verification pins a different identity protocol")
    protocol = _load_identity_protocol(root=root, pin=identity_protocol_pin)
    if protocol.signature_algorithm != verification.signature_algorithm:
        raise ValueError("external verification uses the wrong signature algorithm")
    try:
        signature = base64.b64decode(verification.signature_base64, validate=True)
        key = base64.b64decode(protocol.public_key_base64, validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(
            signature, external_primary_verification_signing_payload(verification)
        )
    except (ValueError, InvalidSignature) as exc:
        raise ValueError("external human-primary signature is invalid") from exc
    return verification


def _load_response_rows(
    *, root: Path, metadata: ReviewArtifactMetadata
) -> list[BlindedReviewRecord]:
    path = _repo_path(root, metadata.responses.path)
    if not path.is_file() or not _hash_matches(path, metadata.responses.sha256):
        raise ValueError(f"review response pin changed: {metadata.responses.path}")
    rows: list[BlindedReviewRecord] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            rows.append(BlindedReviewRecord.model_validate_json(raw))
        except ValueError as exc:
            raise ValueError(f"invalid {path.name} line {line_number}: {exc}") from exc
    return rows


def _validate_citations(
    *, record: BlindedReviewRecord, item: BlindedReviewItem
) -> None:
    lines = item.source_text.splitlines()
    declarations: list[tuple[int, str]] = []
    for line_number, source_line in enumerate(lines, start=1):
        match = re.search(
            r"\bPROGRAM-ID\.\s+([A-Z0-9-]+)\.", source_line, re.IGNORECASE
        )
        if match:
            declarations.append((line_number, match.group(1).upper()))
    for citation in record.review_response.line_level:
        if citation.source_alias != item.source_alias:
            raise ValueError(
                f"citation uses a different source alias: {record.review_item_id}"
            )
        matching_program_spans = []
        for index, (start, program) in enumerate(declarations):
            end = (
                declarations[index + 1][0] - 1
                if index + 1 < len(declarations)
                else len(lines)
            )
            if program == citation.program.upper() and start <= citation.line <= end:
                matching_program_spans.append((start, end))
        if not matching_program_spans:
            raise ValueError(
                f"citation is not localizable in visible source: {record.review_item_id}"
            )


def validate_blinded_review_record(
    *, record: BlindedReviewRecord, item: BlindedReviewItem
) -> None:
    """Validate one response against only its reviewer-visible envelope."""

    if record.review_item_id != item.review_item_id:
        raise ValueError("response review_item_id differs from active envelope")
    _validate_citations(record=record, item=item)


def _index_complete_pass(
    *,
    root: Path,
    rows: list[BlindedReviewRecord],
    metadata: ReviewArtifactMetadata,
    packet_by_id: dict[str, BlindedReviewItem],
) -> dict[str, BlindedReviewRecord]:
    if metadata.expected_item_count != 22 or len(rows) != 22:
        raise ValueError(f"{metadata.review_role} pass must contain exactly 22 items")
    ids = [row.review_item_id for row in rows]
    expected_ids = [
        item.review_item_id
        for item in sorted(packet_by_id.values(), key=lambda item: item.release_ordinal)
    ]
    if len(ids) != len(set(ids)) or ids != expected_ids:
        raise ValueError(
            f"{metadata.review_role} review IDs must exactly follow packet release order"
        )
    if any(row.reviewer_pseudonym != metadata.reviewer_pseudonym for row in rows):
        raise ValueError(
            f"{metadata.review_role} response reviewer differs from metadata"
        )
    for row in rows:
        _validate_citations(record=row, item=packet_by_id[row.review_item_id])
    delivery = _load_delivery_audit(root=root, metadata=metadata)
    if [row.review_item_id for row in delivery] != expected_ids or [
        row.release_ordinal for row in delivery
    ] != list(range(1, 23)):
        raise ValueError("delivery audit differs from exact packet release order")
    for row, audit_row in zip(rows, delivery, strict=True):
        item = packet_by_id[row.review_item_id]
        expected_envelope = item.model_dump_json(indent=2) + "\n"
        if (
            audit_row.source_envelope_sha256
            != hashlib.sha256(expected_envelope.encode("utf-8")).hexdigest()
            or audit_row.response_sha256
            != hashlib.sha256(row.model_dump_json().encode("utf-8")).hexdigest()
        ):
            raise ValueError("delivery audit does not bind the exact envelope/response")
    return {row.review_item_id: row for row in rows}


def _label_key(record: BlindedReviewRecord) -> tuple[object, ...]:
    response = record.review_response
    citations = tuple(
        sorted((ref.program, ref.source_alias, ref.line) for ref in response.line_level)
    )
    return response.decision, response.drift_type, citations


def review_disagreement_dimensions(
    primary: ReviewResponse, verifier: ReviewResponse
) -> tuple[Literal["decision", "drift_type", "line_level"], ...]:
    """Return every difference that must be resolved before promotion.

    Citation coordinates are intentionally part of the gate: different source
    localization is an evidence disagreement even when the coarse label agrees.
    Ordering alone is ignored, while duplicate or coordinate differences remain
    visible through the sorted tuples.
    """

    dimensions: list[Literal["decision", "drift_type", "line_level"]] = []
    if primary.decision != verifier.decision:
        dimensions.append("decision")
    if primary.drift_type != verifier.drift_type:
        dimensions.append("drift_type")
    primary_citations = tuple(
        sorted((ref.program, ref.source_alias, ref.line) for ref in primary.line_level)
    )
    verifier_citations = tuple(
        sorted((ref.program, ref.source_alias, ref.line) for ref in verifier.line_level)
    )
    if primary_citations != verifier_citations:
        dimensions.append("line_level")
    return tuple(dimensions)


def validate_review_evidence(
    *,
    root: Path,
    packet_path: Path,
    packet_sha256: Sha256,
    release_policy_path: Path,
    release_policy_sha256: Sha256,
    evidence: ReviewEvidencePins,
) -> _ValidatedReviewEvidence:
    """Validate both blind passes before any proposal key may be loaded."""

    if not packet_path.is_file() or not _hash_matches(packet_path, packet_sha256):
        raise ValueError("blinded packet pin changed")
    packet = load_blinded_review_packet(packet_path)
    if len(packet) != 22:
        raise ValueError("blinded packet must contain exactly 22 items")
    packet_ids = [item.review_item_id for item in packet]
    if len(packet_ids) != len(set(packet_ids)):
        raise ValueError("blinded packet review IDs must be unique")
    packet_by_id = {item.review_item_id: item for item in packet}
    if (
        not release_policy_path.is_file()
        or not _hash_matches(release_policy_path, release_policy_sha256)
    ):
        raise ValueError("sequential release policy pin changed")
    release_policy = SequentialReleasePolicy.model_validate_json(
        release_policy_path.read_text(encoding="utf-8")
    )

    primary_meta = _load_pinned_metadata(root=root, pin=evidence.ai_primary)
    verifier_meta = _load_pinned_metadata(root=root, pin=evidence.independent_verifier)
    if primary_meta.review_role != "ai_primary":
        raise ValueError("primary metadata must declare ai_primary role")
    if verifier_meta.review_role != "independent_verifier":
        raise ValueError("verification metadata must declare independent_verifier role")
    if primary_meta.reviewer_pseudonym == verifier_meta.reviewer_pseudonym:
        raise ValueError("primary and independent reviewers must be distinct")
    expected_packet_path = packet_path.resolve()
    for meta in (primary_meta, verifier_meta):
        if (
            _repo_path(root, meta.packet.path) != expected_packet_path
            or meta.packet.sha256 != packet_sha256
        ):
            raise ValueError(f"{meta.review_role} metadata pins a different packet")
        if (
            _repo_path(root, meta.release_policy.path) != release_policy_path.resolve()
            or meta.release_policy.sha256 != release_policy_sha256
        ):
            raise ValueError(
                f"{meta.review_role} metadata pins a different release policy"
            )
        if meta.delivery_mode != release_policy.release_mode:
            raise ValueError(f"{meta.review_role} did not attest sequential release")

    primary = _index_complete_pass(
        root=root,
        rows=_load_response_rows(root=root, metadata=primary_meta),
        metadata=primary_meta,
        packet_by_id=packet_by_id,
    )
    verifier = _index_complete_pass(
        root=root,
        rows=_load_response_rows(root=root, metadata=verifier_meta),
        metadata=verifier_meta,
        packet_by_id=packet_by_id,
    )
    primary_audit_pin = primary_meta.controlled_model_audit_manifest
    if primary_audit_pin is None:
        raise ValueError("controlled AI-primary audit manifest is required")
    _validate_controlled_model_audit(
        root=root,
        pin=primary_audit_pin,
        metadata=primary_meta,
        rows=primary,
        packet=packet,
        expected_role="ai_primary",
    )
    verifier_audit_pin = verifier_meta.controlled_model_audit_manifest
    if verifier_audit_pin is None:
        raise ValueError("independent verifier audit manifest is required")
    _validate_controlled_model_audit(
        root=root,
        pin=verifier_audit_pin,
        metadata=verifier_meta,
        rows=verifier,
        packet=packet,
        expected_role="independent_verifier",
    )

    required_adjudications = {
        item_id
        for item_id in packet_by_id
        if primary[item_id].review_response.decision == "needs_adjudication"
        or verifier[item_id].review_response.decision == "needs_adjudication"
        or review_disagreement_dimensions(
            primary[item_id].review_response,
            verifier[item_id].review_response,
        )
    }
    adjudication: dict[str, BlindedReviewRecord] = {}
    adjudicator_meta: ReviewArtifactMetadata | None = None
    adjudication_audit_pin: ArtifactPin | None = None
    adjudication_bridge_pin: ArtifactPin | None = None
    correction_audit_pin: ArtifactPin | None = None
    correction_bridge_pin: ArtifactPin | None = None
    correction_responses_pin: ArtifactPin | None = None
    correction_pair_members: dict[str, tuple[str, str]] = {}
    replacement_audit_pin: ArtifactPin | None = None
    replacement_bridge_pin: ArtifactPin | None = None
    replacement_plan_pin: ArtifactPin | None = None
    replacement_responses_pin: ArtifactPin | None = None
    replacement_pairs: list[tuple[object, object]] = []
    if evidence.adjudication is not None:
        adjudicator_meta = _load_pinned_metadata(root=root, pin=evidence.adjudication)
        if adjudicator_meta.review_role != "adjudicator":
            raise ValueError("adjudication metadata must declare adjudicator role")
        if adjudicator_meta.reviewer_pseudonym in {
            primary_meta.reviewer_pseudonym,
            verifier_meta.reviewer_pseudonym,
        }:
            raise ValueError("adjudicator must be distinct from both reviewers")
        if (
            _repo_path(root, adjudicator_meta.packet.path) != expected_packet_path
            or adjudicator_meta.packet.sha256 != packet_sha256
        ):
            raise ValueError("adjudicator metadata pins a different packet")
        if (
            _repo_path(root, adjudicator_meta.release_policy.path)
            != release_policy_path.resolve()
            or adjudicator_meta.release_policy.sha256 != release_policy_sha256
        ):
            raise ValueError("adjudicator metadata pins a different release policy")
        rows = _load_response_rows(root=root, metadata=adjudicator_meta)
        ids = [row.review_item_id for row in rows]
        if (
            adjudicator_meta.expected_item_count != len(required_adjudications)
            or len(ids) != len(set(ids))
            or set(ids) != required_adjudications
        ):
            raise ValueError("adjudication must exactly cover every disputed item")
        for row in rows:
            if row.reviewer_pseudonym != adjudicator_meta.reviewer_pseudonym:
                raise ValueError("adjudication reviewer differs from metadata")
            if row.review_response.decision == "needs_adjudication":
                raise ValueError(
                    "adjudication must make a final include/exclude decision"
                )
            _validate_citations(record=row, item=packet_by_id[row.review_item_id])
        adjudication = {row.review_item_id: row for row in rows}
        delivery = _load_delivery_audit(root=root, metadata=adjudicator_meta)
        if [row.review_item_id for row in delivery] != ids or [
            row.release_ordinal for row in delivery
        ] != [packet_by_id[item_id].release_ordinal for item_id in ids]:
            raise ValueError("adjudication delivery differs from disputed item order")
        for row, audit_row in zip(rows, delivery, strict=True):
            item = packet_by_id[row.review_item_id]
            expected_envelope = item.model_dump_json(indent=2) + "\n"
            if (
                audit_row.source_envelope_sha256
                != hashlib.sha256(expected_envelope.encode("utf-8")).hexdigest()
                or audit_row.response_sha256
                != hashlib.sha256(row.model_dump_json().encode("utf-8")).hexdigest()
            ):
                raise ValueError(
                    "adjudication delivery does not bind the exact envelope/response"
                )
        if required_adjudications:
            if evidence.ai_adjudication_bridge_manifest is None:
                raise ValueError(
                    "disputed adjudication requires a validated AI audit bridge"
                )
            from cobol_archaeologist.benchmark.t6_adjudication import (
                validate_ai_adjudication_audit,
            )
            from cobol_archaeologist.benchmark.t6_adjudication_bridge import (
                validate_ai_adjudication_promotion_bridge,
            )

            bridge_path = _check_pin(
                root,
                evidence.ai_adjudication_bridge_manifest,
                label="AI adjudication promotion bridge",
            )
            bridge = validate_ai_adjudication_promotion_bridge(
                root=root, bridge_path=bridge_path
            )
            if (
                bridge.adjudication_metadata.model_dump(mode="json")
                != evidence.adjudication.model_dump(mode="json")
            ):
                raise ValueError("AI adjudication bridge pins different metadata")
            audit_path = _check_pin(
                root,
                bridge.adjudication_audit_manifest,
                label="AI adjudication audit",
            )
            audit = validate_ai_adjudication_audit(
                root=root, manifest_path=audit_path
            )
            if (
                audit.primary_responses
                != _controlled_source_responses(root=root, metadata=primary_meta)
                or audit.independent_responses
                != _controlled_source_responses(root=root, metadata=verifier_meta)
                or audit.packet != adjudicator_meta.packet
                or audit.responses.path == adjudicator_meta.responses.path
            ):
                raise ValueError(
                    "AI adjudication audit differs from active review evidence"
                )
            adjudication_audit_pin = bridge.adjudication_audit_manifest
            adjudication_bridge_pin = evidence.ai_adjudication_bridge_manifest
    elif required_adjudications:
        raise ValueError("disagreements require a pinned adjudication artifact")
    elif evidence.ai_adjudication_bridge_manifest is not None:
        raise ValueError("zero-dispute evidence cannot attach an adjudication bridge")

    if evidence.pair_correction_bridge_manifest is not None:
        if adjudicator_meta is None:
            raise ValueError("pair correction requires the sealed base adjudication")
        from cobol_archaeologist.benchmark.t6_pair_correction import (
            validate_pair_correction_audit,
            validate_pair_correction_bridge,
        )

        correction_bridge_path = _check_pin(
            root,
            evidence.pair_correction_bridge_manifest,
            label="pair correction bridge",
        )
        correction_bridge, correction_rows = validate_pair_correction_bridge(
            root=root, bridge_path=correction_bridge_path
        )
        correction_audit_path = _check_pin(
            root,
            correction_bridge.correction_audit_manifest,
            label="pair correction audit",
        )
        correction_audit = validate_pair_correction_audit(
            root=root, manifest_path=correction_audit_path
        )
        if (
            correction_audit.primary_responses != primary_meta.responses
            or correction_audit.adjudication_responses
            != adjudicator_meta.responses
        ):
            raise ValueError("pair correction uses different sealed base judgments")
        correction_ids = {row.review_item_id for row in correction_rows}
        if len(correction_ids) != 2 * len(correction_bridge.pair_members):
            raise ValueError("pair correction projection side count is inconsistent")
        adjudication.update({row.review_item_id: row for row in correction_rows})
        correction_audit_pin = correction_bridge.correction_audit_manifest
        correction_bridge_pin = evidence.pair_correction_bridge_manifest
        correction_responses_pin = correction_bridge.correction_responses
        correction_pair_members = {
            key: value for key, value in correction_bridge.pair_members.items()
        }

    if evidence.replacement_bridge_manifest is not None:
        from cobol_archaeologist.benchmark.t6_replacement import (
            validate_replacement_bridge,
        )

        replacement_bridge_path = _check_pin(
            root,
            evidence.replacement_bridge_manifest,
            label="replacement bridge",
        )
        replacement_bridge, replacement_pairs = validate_replacement_bridge(
            root=root, bridge_path=replacement_bridge_path
        )
        replacement_audit_pin = replacement_bridge.replacement_audit
        replacement_bridge_pin = evidence.replacement_bridge_manifest
        replacement_plan_pin = replacement_bridge.replacement_plan
        replacement_responses_pin = replacement_bridge.replacement_responses

    pins = PromotionReviewEvidencePins(
        ai_primary_metadata=evidence.ai_primary,
        ai_primary_responses=primary_meta.responses,
        ai_primary_audit_manifest=primary_audit_pin,
        independent_verifier_metadata=evidence.independent_verifier,
        independent_verifier_responses=verifier_meta.responses,
        adjudication_metadata=evidence.adjudication,
        adjudication_responses=(
            adjudicator_meta.responses if adjudicator_meta is not None else None
        ),
        ai_adjudication_audit_manifest=adjudication_audit_pin,
        ai_adjudication_bridge_manifest=adjudication_bridge_pin,
        independent_verifier_audit_manifest=verifier_audit_pin,
        pair_correction_audit_manifest=correction_audit_pin,
        pair_correction_bridge_manifest=correction_bridge_pin,
        pair_correction_responses=correction_responses_pin,
        replacement_audit_manifest=replacement_audit_pin,
        replacement_bridge_manifest=replacement_bridge_pin,
        replacement_plan=replacement_plan_pin,
        replacement_responses=replacement_responses_pin,
    )

    return _ValidatedReviewEvidence(
        packet=packet,
        primary=primary,
        verifier=verifier,
        adjudication=adjudication,
        pins=pins,
        controlled_ai_primary_verified=True,
        correction_pair_members=correction_pair_members,
        replacement_pairs=replacement_pairs,
    )


def _resolved_record(
    item_id: str, evidence: _ValidatedReviewEvidence
) -> BlindedReviewRecord:
    return evidence.adjudication.get(item_id, evidence.primary[item_id])


def _load_carried_instances(
    *, root: Path, manifest: T6V2Manifest
) -> list[DriftInstance]:
    split = _repo_path(root, manifest.source_benchmark.path)
    rows = {
        row.instance_id: row
        for raw in split.read_text(encoding="utf-8").splitlines()
        if raw.strip()
        for row in [DriftInstance.model_validate_json(raw)]
    }
    return [
        rows[side.instance_id]
        for pair in manifest.carried_forward_pairs
        for side in pair.sides
    ]


def _candidate_ids(proposals: list[CandidatePairProposal]) -> list[str]:
    count = sum(len(pair.sides) for pair in proposals)
    return [f"drift_{120001 + offset:06d}" for offset in range(count)]


def _proposal_matches_review(
    *,
    side: CandidateSideProposal,
    item: BlindedReviewItem,
    record: BlindedReviewRecord,
) -> bool:
    response = record.review_response
    if (
        response.decision != "include"
        or response.drift_type != side.proposed_drift_type
    ):
        return False
    review_refs = _canonical_review_lines(side=side, item=item, record=record)
    if review_refs is None:
        return False
    proposal_lines = sorted(
        (ref.program, ref.file or "", ref.line)
        for ref in side.proposed_labels.line_level
    )
    review_lines = sorted(
        (ref.program, ref.file or "", ref.line) for ref in review_refs
    )
    return proposal_lines == review_lines


def _canonical_review_lines(
    *, side: CandidateSideProposal, item: BlindedReviewItem, record: BlindedReviewRecord
) -> list[SourceLineRef] | None:
    refs: list[SourceLineRef] = []
    for citation in record.review_response.line_level:
        if citation.source_alias != item.source_alias:
            return None
        loci = [
            locus
            for locus in side.code_locus.loci
            if locus.program == citation.program
            and locus.line_span[0] <= citation.line <= locus.line_span[1]
        ]
        if len(loci) != 1:
            return None
        refs.append(
            SourceLineRef(
                program=citation.program,
                line=citation.line,
                file=loci[0].file,
            )
        )
    return refs


def _canonical_replacement_review_lines(
    *,
    code_locus: CodeLocus,
    expected_source_alias: str,
    response: ReviewResponse,
) -> list[SourceLineRef]:
    """Project full-source replacement citations into the frozen scoring locus.

    Replacement reviewers see the complete pinned source and may cite supporting
    declarations outside the narrower procedure locus. The sealed replacement
    validator already proves that every citation belongs to a visible program;
    promotion retains only citations that can be mapped unambiguously into the
    scoring locus. A non-conformant side still fails closed unless at least one
    in-locus citation remains.
    """

    refs: list[SourceLineRef] = []
    for citation in response.line_level:
        if citation.source_alias != expected_source_alias:
            raise ValueError("replacement citation uses the wrong source alias")
        loci = [
            locus
            for locus in code_locus.loci
            if locus.program == citation.program
            and locus.line_span[0] <= citation.line <= locus.line_span[1]
        ]
        if len(loci) > 1:
            raise ValueError("replacement citation maps to multiple loci")
        if len(loci) == 1:
            refs.append(
                SourceLineRef(
                    program=citation.program,
                    line=citation.line,
                    file=loci[0].file,
                )
            )
    if response.drift_type != "D7_conformant" and not refs:
        raise ValueError("replacement has no citation in the frozen code locus")
    return refs


def build_t6_review_promotion(
    *, root: Path, manifest_path: Path, evidence: ReviewEvidencePins
) -> T6ReviewPromotionReport:
    """Evaluate promotion without modifying v1 or writing canonical output.

    The ordering here is security-relevant: review evidence is fully validated
    before ``pair_proposals.jsonl`` is read or its labels are inspected.
    """

    manifest = load_t6_v2_manifest(manifest_path)
    packet_path = _repo_path(root, manifest.blinded_review_packet.path)
    validated = validate_review_evidence(
        root=root,
        packet_path=packet_path,
        packet_sha256=manifest.blinded_review_packet.sha256,
        release_policy_path=_repo_path(root, manifest.blind_release_policy.path),
        release_policy_sha256=manifest.blind_release_policy.sha256,
        evidence=evidence,
    )

    # Opening the sealed key is forbidden above this point.
    validate_t6_v2(root=root, manifest_path=manifest_path)
    proposal_path = _repo_path(root, manifest.candidate_proposals.path)
    proposals = sorted(
        load_candidate_pair_proposals(proposal_path), key=lambda pair: pair.pair_id
    )
    if validated.correction_pair_members:
        expected_corrections = {
            pair.pair_id: tuple(
                side.blind_review_id
                for side in sorted(pair.sides, key=lambda item: item.candidate_side_id)
            )
            for pair in proposals
            if pair.pair_id in validated.correction_pair_members
        }
        if expected_corrections != validated.correction_pair_members:
            raise ValueError("pair correction scope differs from sealed candidate pairs")
    carried = _load_carried_instances(root=root, manifest=manifest)
    proposed_ids = _candidate_ids(proposals)
    packet_by_id = {item.review_item_id: item for item in validated.packet}
    original_gaps: list[PromotionGap] = []
    eligible_entries: list[dict[str, object]] = []

    for pair in proposals:
        pair_ok = True
        verdicts: set[bool] = set()
        side_rows: list[dict[str, object]] = []
        for side in sorted(pair.sides, key=lambda item: item.candidate_side_id):
            record = _resolved_record(side.blind_review_id, validated)
            response = record.review_response
            if response.decision == "exclude":
                original_gaps.append(
                    PromotionGap(
                        code="excluded",
                        review_item_id=side.blind_review_id,
                        pair_id=pair.pair_id,
                        detail="final review excluded this side",
                    )
                )
                pair_ok = False
                continue
            if response.decision != "include" or response.drift_type is None:
                original_gaps.append(
                    PromotionGap(
                        code="unresolved",
                        review_item_id=side.blind_review_id,
                        pair_id=pair.pair_id,
                        detail="final review did not resolve to an included label",
                    )
                )
                pair_ok = False
                continue
            review_lines = _canonical_review_lines(
                side=side,
                item=packet_by_id[side.blind_review_id],
                record=record,
            )
            if review_lines is None:
                original_gaps.append(
                    PromotionGap(
                        code="proposal_mismatch",
                        review_item_id=side.blind_review_id,
                        pair_id=pair.pair_id,
                        detail="resolved citations fall outside the sealed code locus",
                    )
                )
                pair_ok = False
            else:
                side_rows.append(
                    {
                        "authority": side.authority,
                        "code_locus": side.code_locus,
                        "response": response,
                        "review_lines": review_lines,
                    }
                )
            verdicts.add(response.drift_type != "D7_conformant")
        if verdicts != {False, True}:
            original_gaps.append(
                PromotionGap(
                    code="pair_ineligible",
                    pair_id=pair.pair_id,
                    detail="pair must resolve to one D7 and one non-D7 side",
                )
            )
            pair_ok = False
        if pair_ok:
            eligible_entries.append(
                {
                    "pair_id": pair.pair_id,
                    "target": {
                        "P3": "grievance_response_deadline",
                        "P4": "partnership_beneficial_owner_threshold",
                        "P5": "central_kyc_update_deadline",
                    }[pair.period],
                    "source": ArtifactPin(
                        path=pair.code_input_path, sha256=pair.code_sha256
                    ),
                    "base_program": Path(pair.code_input_path).name,
                    "sides": side_rows,
                    "notes": "T6-v2 blinded primary, verification, and adjudication gate",
                }
            )

    for plan_value, completion_value in validated.replacement_pairs:
        from cobol_archaeologist.benchmark.t6_replacement import (
            ReplacementCompletion,
            ReplacementPlanItem,
        )

        plan = ReplacementPlanItem.model_validate(plan_value)
        completion = ReplacementCompletion.model_validate(completion_value)
        replacement_sides: list[dict[str, object]] = []
        for side_input, side_output in zip(
            plan.sides, completion.sides, strict=True
        ):
            refs = _canonical_replacement_review_lines(
                code_locus=plan.code_locus,
                expected_source_alias=side_input.source_alias,
                response=side_output.review_response,
            )
            replacement_sides.append(
                {
                    "authority": side_input.authority,
                    "code_locus": plan.code_locus,
                    "response": side_output.review_response,
                    "review_lines": refs,
                }
            )
        target = (
            "grievance_response_deadline"
            if plan.rejected_pair_id in {
                "t6v2-candidate-01",
                "t6v2-candidate-02",
                "t6v2-candidate-03",
            }
            else "partnership_beneficial_owner_threshold"
            if plan.rejected_pair_id
            in {"t6v2-candidate-04", "t6v2-candidate-05"}
            else "central_kyc_update_deadline"
        )
        eligible_entries.append(
            {
                "pair_id": plan.replacement_id,
                "target": target,
                "source": plan.source,
                "base_program": Path(plan.source.path).name,
                "sides": replacement_sides,
                "notes": "T6-v2 additive proposal-blind replacement review gate",
            }
        )

    selected_entries = eligible_entries[:11]
    labels_ready = len(selected_entries) == 11
    gaps: list[PromotionGap] = [] if labels_ready else original_gaps
    if not labels_ready:
        gaps.append(
            PromotionGap(
                code="pair_ineligible",
                detail=(
                    f"eligible temporal pool has {len(eligible_entries)} pairs; "
                    "11 add-on pairs are required"
                ),
            )
        )
    if validated.pins.adjudication_metadata is None:
        gaps.append(
            PromotionGap(
                code="adjudication_evidence_missing",
                detail="an explicit adjudication or zero-dispute record is required",
            )
        )
    ready = (
        labels_ready
        and validated.controlled_ai_primary_verified
        and validated.pins.adjudication_metadata is not None
        and validated.pins.adjudication_responses is not None
    )
    candidates: list[DriftInstance] = []
    if ready:
        next_id = iter(proposed_ids)
        for entry in selected_entries:
            for side_row in entry["sides"]:
                assert isinstance(side_row, dict)
                response = ReviewResponse.model_validate(side_row["response"])
                assert response.drift_type is not None
                conformant = response.drift_type == "D7_conformant"
                review_lines = [
                    SourceLineRef.model_validate(item)
                    for item in side_row["review_lines"]
                ]
                candidates.append(
                    DriftInstance(
                        instance_id=next(next_id),
                        regulation_clause=side_row["authority"],
                        code_locus=side_row["code_locus"],
                        drift_type=response.drift_type,
                        target_path=None,
                        labels=Labels(
                            program_level="conformant" if conformant else "drift",
                            paragraph_level="conformant" if conformant else "drift",
                            line_level=review_lines,
                        ),
                        gold_rationale=response.rationale,
                        provenance=Provenance(
                            source="real_curated",
                            base_program=str(entry["base_program"]),
                            mutation=None,
                            annotator_notes=(
                                str(entry["notes"])
                            ),
                        ),
                    )
                )

    source_inputs: dict[str, ArtifactPin] = {}
    for pair in manifest.carried_forward_pairs:
        for side in pair.sides:
            source_inputs[side.instance_id] = ArtifactPin(
                path=pair.code_input_path, sha256=pair.code_sha256
            )
    if ready:
        candidate_sources = (
            entry["source"] for entry in selected_entries for _ in range(2)
        )
        for instance_id, source in zip(proposed_ids, candidate_sources, strict=True):
            source_inputs[instance_id] = ArtifactPin.model_validate(source)
    else:
        candidate_sides = (
            (pair, side)
            for pair in proposals
            for side in sorted(pair.sides, key=lambda item: item.candidate_side_id)
        )
        for instance_id, (pair, _) in zip(proposed_ids, candidate_sides, strict=True):
            source_inputs[instance_id] = ArtifactPin(
                path=pair.code_input_path, sha256=pair.code_sha256
            )

    pair_members = {
        pair.pair_id: [side.instance_id for side in pair.sides]
        for pair in manifest.carried_forward_pairs
    }
    candidate_member_ids = iter(proposed_ids)
    selected_pair_ids = (
        [str(entry["pair_id"]) for entry in selected_entries]
        if ready
        else [pair.pair_id for pair in proposals]
    )
    for pair_id in selected_pair_ids:
        pair_members[pair_id] = [
            next(candidate_member_ids),
            next(candidate_member_ids),
        ]
    target_by_period: dict[str, AuthorityTarget] = {
        "P3": "grievance_response_deadline",
        "P4": "partnership_beneficial_owner_threshold",
        "P5": "central_kyc_update_deadline",
    }
    authority_targets: dict[str, AuthorityTarget] = {
        pair.pair_id: target_by_period[pair.period]
        for pair in manifest.carried_forward_pairs
    }
    if ready:
        authority_targets.update(
            {
                str(entry["pair_id"]): entry["target"]
                for entry in selected_entries
            }
        )
    else:
        authority_targets.update(
            {pair.pair_id: target_by_period[pair.period] for pair in proposals}
        )
    manifest_relative = manifest_path.resolve().relative_to(root.resolve()).as_posix()

    return T6ReviewPromotionReport(
        evaluation_ready=ready,
        target_pair_count=20,
        evaluation_eligible_pair_count=20 if ready else 9,
        carried_pair_count=9,
        candidate_pair_count=11,
        review_item_count=22,
        resolved_candidate_pairs=min(len(eligible_entries), 11),
        gaps=gaps,
        proposed_pair_order=[
            *(pair.pair_id for pair in manifest.carried_forward_pairs),
            *selected_pair_ids,
        ],
        proposed_candidate_instance_ids=proposed_ids,
        proposed_instance_order=[
            *(row.instance_id for row in carried),
            *proposed_ids,
        ],
        proposed_pair_members=pair_members,
        proposed_authority_targets=authority_targets,
        proposed_source_inputs=source_inputs,
        preparation_manifest=ArtifactPin(
            path=manifest_relative, sha256=_sha256(manifest_path)
        ),
        review_evidence=validated.pins,
        carried_instances=carried,
        candidate_instances=candidates,
        controlled_ai_primary_verified=validated.controlled_ai_primary_verified,
    )


def propose_t6_finalized_manifest(
    *,
    root: Path,
    report: T6ReviewPromotionReport,
    promotion_report: ArtifactPin,
    evaluation_rows: ArtifactPin,
) -> T6FinalizedManifestProposal:
    """Bind a successful report to a prospective 40-row JSONL artifact pin.

    All input pins are re-read and hash-checked here. The caller remains
    responsible only for durably writing the returned canonical manifest.
    """

    if (
        not report.evaluation_ready
        or not report.controlled_ai_primary_verified
        or len(report.candidate_instances) != 22
    ):
        raise ValueError("cannot propose a finalized manifest from a failed gate")
    review = report.review_evidence
    if review.adjudication_metadata is None or review.adjudication_responses is None:
        raise ValueError("finalization requires complete pinned review evidence")
    required_pins = [
        report.preparation_manifest,
        promotion_report,
        review.ai_primary_metadata,
        review.ai_primary_responses,
        review.ai_primary_audit_manifest,
        review.independent_verifier_metadata,
        review.independent_verifier_responses,
        review.adjudication_metadata,
        review.adjudication_responses,
        review.ai_adjudication_audit_manifest,
        review.ai_adjudication_bridge_manifest,
        review.independent_verifier_audit_manifest,
        review.pair_correction_audit_manifest,
        review.pair_correction_bridge_manifest,
        review.pair_correction_responses,
        review.replacement_audit_manifest,
        review.replacement_bridge_manifest,
        review.replacement_plan,
        review.replacement_responses,
        evaluation_rows,
        *report.proposed_source_inputs.values(),
    ]
    for pin in (item for item in required_pins if item is not None):
        path = _repo_path(root, pin.path)
        if not path.is_file() or not _hash_matches(path, pin.sha256):
            raise ValueError(f"finalization artifact pin changed: {pin.path}")
    pinned_report = T6ReviewPromotionReport.model_validate_json(
        _repo_path(root, promotion_report.path).read_text(encoding="utf-8")
    )
    if pinned_report.model_dump(mode="json") != report.model_dump(mode="json"):
        raise ValueError("promotion report pin does not contain the successful report")
    all_rows = [*report.carried_instances, *report.candidate_instances]
    if [row.instance_id for row in all_rows] != report.proposed_instance_order:
        raise ValueError("promotion rows differ from deterministic instance order")
    pinned_rows = [
        DriftInstance.model_validate_json(line)
        for line in _repo_path(root, evaluation_rows.path)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if pinned_rows != all_rows:
        raise ValueError("evaluation_rows pin differs from successful promotion rows")
    return T6FinalizedManifestProposal(
        schema_version="1",
        finalized=True,
        evaluation_ready=True,
        evaluation_rows=evaluation_rows,
        preparation_manifest=report.preparation_manifest,
        promotion_report=promotion_report,
        review_evidence=FinalizedReviewEvidencePins(
            ai_primary_metadata=review.ai_primary_metadata,
            ai_primary_responses=review.ai_primary_responses,
            ai_primary_audit_manifest=review.ai_primary_audit_manifest,
            independent_verifier_metadata=review.independent_verifier_metadata,
            independent_verifier_responses=review.independent_verifier_responses,
            adjudication_metadata=review.adjudication_metadata,
            adjudication_responses=review.adjudication_responses,
            ai_adjudication_audit_manifest=(
                review.ai_adjudication_audit_manifest
            ),
            ai_adjudication_bridge_manifest=(
                review.ai_adjudication_bridge_manifest
            ),
            independent_verifier_audit_manifest=(
                review.independent_verifier_audit_manifest
            ),
            pair_correction_audit_manifest=review.pair_correction_audit_manifest,
            pair_correction_bridge_manifest=review.pair_correction_bridge_manifest,
            pair_correction_responses=review.pair_correction_responses,
            replacement_audit_manifest=review.replacement_audit_manifest,
            replacement_bridge_manifest=review.replacement_bridge_manifest,
            replacement_plan=review.replacement_plan,
            replacement_responses=review.replacement_responses,
        ),
        controlled_ai_primary_verified=True,
        target_pair_count=20,
        evaluation_side_count=40,
        pair_order=report.proposed_pair_order,
        instance_order=report.proposed_instance_order,
        pair_members=report.proposed_pair_members,
        authority_targets=report.proposed_authority_targets,
        source_inputs=report.proposed_source_inputs,
    )
