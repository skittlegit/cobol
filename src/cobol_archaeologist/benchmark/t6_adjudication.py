"""Byte-exact non-human adjudication evidence for disputed T6 review items."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    CollaborationSubagentAttemptAudit,
    ReviewResponse,
    validate_blinded_review_record,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    load_blinded_review_packet,
)

Sha256 = str
DisagreementDimension = Literal["decision", "drift_type", "line_level"]


class AIAdjudicationResponseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    review_role: Literal["ai_adjudicator"]
    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    task_identity: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    review_response: ReviewResponse

    @model_validator(mode="after")
    def _decision_is_final(self) -> AIAdjudicationResponseRecord:
        if self.review_response.decision == "needs_adjudication":
            raise ValueError("AI adjudication must make a final decision")
        return self


class AIAdjudicationItemAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    source_alias: str = Field(pattern=r"^src-[0-9a-f]{12}$")
    source_envelope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independent_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    disagreement_dimensions: list[DisagreementDimension] = Field(min_length=1)
    adjudication_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempts: list[CollaborationSubagentAttemptAudit] = Field(min_length=1)

    @model_validator(mode="after")
    def _attempt_chain_is_complete(self) -> AIAdjudicationItemAudit:
        if [attempt.attempt for attempt in self.attempts] != list(
            range(1, len(self.attempts) + 1)
        ):
            raise ValueError("adjudication attempts must be contiguous from one")
        if self.attempts[-1].outcome != "accepted" or any(
            attempt.outcome != "schema_invalid" for attempt in self.attempts[:-1]
        ):
            raise ValueError("adjudication attempts must end in one accepted response")
        return self


class AIAdjudicationAuditManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    audit_variant: Literal["ai_adjudicator_collaboration_subagent"]
    finalized: Literal[True]
    review_role: Literal["ai_adjudicator"]
    reviewer_pseudonym: str = Field(min_length=1)
    comparison_report: ArtifactPin
    packet: ArtifactPin
    response_schema: ArtifactPin
    primary_responses: ArtifactPin
    independent_responses: ArtifactPin
    responses: ArtifactPin
    provider: Literal["chatgpt-codex-collaboration"]
    model_id: Literal["gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    fork_turns_per_attempt: Literal["none"]
    fresh_task_per_attempt: Literal[True]
    visible_review_items_per_call: Literal[1]
    staged_source_bundles_per_call: Literal[0]
    tools_authorized_per_call: Literal[0]
    prior_item_context_included: Literal[False]
    native_execution_bundle_claimed: Literal[False]
    item_count: int = Field(ge=1, le=22)
    accepted_count: int = Field(ge=1, le=22)
    schema_invalid_attempt_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    release_ordinal_order: list[int]
    review_item_order: list[str]
    items: list[AIAdjudicationItemAudit]

    @model_validator(mode="after")
    def _summary_matches_items(self) -> AIAdjudicationAuditManifest:
        if (
            self.item_count != len(self.items)
            or self.accepted_count != len(self.items)
            or self.release_ordinal_order
            != [item.release_ordinal for item in self.items]
            or self.review_item_order != [item.review_item_id for item in self.items]
        ):
            raise ValueError("adjudication manifest order/count differs from items")
        invalid = sum(
            attempt.outcome == "schema_invalid"
            for item in self.items
            for attempt in item.attempts
        )
        if self.schema_invalid_attempt_count != invalid or self.retry_count != invalid:
            raise ValueError("adjudication retry counts differ from attempts")
        tasks = [
            attempt.task_identity for item in self.items for attempt in item.attempts
        ]
        if len(tasks) != len(set(tasks)):
            raise ValueError("adjudication task identities must be unique")
        return self


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_pin(root: Path, pin: ArtifactPin, *, label: str) -> Path:
    path = (root / pin.path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"{label} leaves the repository or is missing")
    if _sha(path) != pin.sha256:
        raise ValueError(f"{label} pin changed")
    return path


def _response_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw]


def _compact(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def validate_ai_adjudication_audit(
    *, root: Path, manifest_path: Path
) -> AIAdjudicationAuditManifest:
    """Recompute every visible input and exact output in an adjudication pass."""

    manifest = AIAdjudicationAuditManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    comparison_path = _check_pin(root, manifest.comparison_report, label="comparison")
    packet_path = _check_pin(root, manifest.packet, label="packet")
    _check_pin(root, manifest.response_schema, label="response schema")
    primary_path = _check_pin(root, manifest.primary_responses, label="primary responses")
    independent_path = _check_pin(
        root, manifest.independent_responses, label="independent responses"
    )
    responses_path = _check_pin(root, manifest.responses, label="adjudication responses")
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    disputed = [
        row for row in comparison["items"] if row["requires_adjudication_review"]
    ]
    packet = load_blinded_review_packet(packet_path)
    packet_by_id = {item.review_item_id: item for item in packet}
    primary = {row["review_item_id"]: row for row in _response_rows(primary_path)}
    independent = {
        row["review_item_id"]: row for row in _response_rows(independent_path)
    }
    responses = [
        AIAdjudicationResponseRecord.model_validate_json(raw)
        for raw in responses_path.read_text(encoding="utf-8").splitlines()
        if raw
    ]
    if len(disputed) != manifest.item_count or len(responses) != manifest.item_count:
        raise ValueError("adjudication must exactly cover every disputed item")
    for dispute, audit, response in zip(
        disputed, manifest.items, responses, strict=True
    ):
        item = packet_by_id[dispute["review_item_id"]]
        visible = {
            "review_item_id": item.review_item_id,
            "authority": item.authority.model_dump(mode="json"),
            "source_alias": item.source_alias,
            "source_text": item.source_text,
        }
        visible_bytes = _compact(visible)
        primary_response = primary[item.review_item_id]["review_response"]
        independent_response = independent[item.review_item_id]["review_response"]
        primary_bytes = _compact(primary_response)
        independent_bytes = _compact(independent_response)
        dimensions_bytes = _compact(dispute["disagreement_dimensions"])
        input_bytes = b"\n".join(
            [visible_bytes, primary_bytes, independent_bytes, dimensions_bytes]
        )
        accepted = audit.attempts[-1]
        final = base64.b64decode(accepted.final_message_utf8_base64, validate=True)
        parsed = ReviewResponse.model_validate_json(final)
        prompt = base64.b64decode(accepted.prompt_utf8_base64, validate=True)
        markers = [
            b"Envelope: " + visible_bytes,
            b"Primary response: " + primary_bytes,
            b"Independent response: " + independent_bytes,
            b"Disagreement dimensions: " + dimensions_bytes,
        ]
        if (
            audit.release_ordinal != dispute["release_ordinal"]
            or audit.review_item_id != item.review_item_id
            or audit.source_alias != item.source_alias
            or audit.source_envelope_sha256
            != hashlib.sha256(visible_bytes).hexdigest()
            or audit.primary_response_sha256
            != hashlib.sha256(primary_bytes).hexdigest()
            or audit.independent_response_sha256
            != hashlib.sha256(independent_bytes).hexdigest()
            or audit.disagreement_dimensions != dispute["disagreement_dimensions"]
            or audit.adjudication_input_sha256
            != hashlib.sha256(input_bytes).hexdigest()
            or response.release_ordinal != audit.release_ordinal
            or response.review_item_id != audit.review_item_id
            or response.task_identity != accepted.task_identity
            or response.attempt != accepted.attempt
            or response.review_response != parsed
            or accepted.model_id != "gpt-5.6-luna"
            or prompt.count(b"Envelope:") != 1
            or any(prompt.count(marker) != 1 for marker in markers)
        ):
            raise ValueError("AI adjudication evidence differs from frozen inputs")
        validate_blinded_review_record(
            record=BlindedReviewRecord(
                review_item_id=item.review_item_id,
                reviewer_pseudonym=manifest.reviewer_pseudonym,
                completed_at="1970-01-01T00:00:00Z",
                review_response=parsed,
            ),
            item=item,
        )
    return manifest
