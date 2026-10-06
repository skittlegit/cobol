"""Deterministic projection of AI-adjudication evidence into promotion inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.benchmark.t6_adjudication import (
    AIAdjudicationResponseRecord,
    validate_ai_adjudication_audit,
)
from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    ReviewArtifactMetadata,
    SequentialDeliveryAuditEntry,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    SequentialReleasePolicy,
    artifact_sha256_matches,
    load_blinded_review_packet,
)

PROJECTION_COMPLETED_AT = "1970-01-01T00:00:00Z"


class AIAdjudicationPromotionBridgeManifest(BaseModel):
    """Pins the validated source audit and every deterministic projection output."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    finalized: Literal[True]
    projection: Literal["ai_adjudication_to_t6_promotion_v1"]
    adjudication_audit_manifest: ArtifactPin
    adjudication_metadata: ArtifactPin
    adjudication_responses: ArtifactPin
    sequential_delivery_audit: ArtifactPin
    reviewer_pseudonym: str = Field(min_length=1)
    item_count: int = Field(ge=1, le=22)
    release_ordinal_order: list[int]
    review_item_order: list[str]
    projection_completed_at: Literal["1970-01-01T00:00:00Z"] = (
        PROJECTION_COMPLETED_AT
    )

    @model_validator(mode="after")
    def _orders_match_count(self) -> AIAdjudicationPromotionBridgeManifest:
        if (
            self.item_count != len(self.release_ordinal_order)
            or self.item_count != len(self.review_item_order)
            or len(set(self.release_ordinal_order)) != self.item_count
            or len(set(self.review_item_order)) != self.item_count
        ):
            raise ValueError("adjudication bridge order/count is inconsistent")
        return self


def _canonical_bytes(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"adjudication bridge path leaves repository: {relative}")
    return path


def _pin(root: Path, path: Path) -> ArtifactPin:
    return ArtifactPin(
        path=path.resolve().relative_to(root.resolve()).as_posix(), sha256=_sha(path)
    )


def _check_pin(root: Path, pin: ArtifactPin, *, label: str) -> Path:
    path = _repo_path(root, pin.path)
    if not path.is_file() or not artifact_sha256_matches(path, pin.sha256):
        raise ValueError(f"{label} pin changed")
    return path


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"refusing to replace adjudication bridge output: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _projected_rows(
    *, responses_path: Path, reviewer_pseudonym: str
) -> list[BlindedReviewRecord]:
    source = [
        AIAdjudicationResponseRecord.model_validate_json(raw)
        for raw in responses_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    return [
        BlindedReviewRecord(
            review_item_id=row.review_item_id,
            reviewer_pseudonym=reviewer_pseudonym,
            completed_at=PROJECTION_COMPLETED_AT,
            review_response=row.review_response,
        )
        for row in source
    ]


def _jsonl(rows: list[BaseModel]) -> bytes:
    return b"".join((row.model_dump_json() + "\n").encode("utf-8") for row in rows)


def _delivery_rows(
    *, packet_path: Path, responses: list[BlindedReviewRecord]
) -> list[SequentialDeliveryAuditEntry]:
    packet = {
        item.review_item_id: item for item in load_blinded_review_packet(packet_path)
    }
    result: list[SequentialDeliveryAuditEntry] = []
    previous: str | None = None
    for response in responses:
        item = packet[response.review_item_id]
        entry = SequentialDeliveryAuditEntry(
            schema_version="1",
            release_ordinal=item.release_ordinal,
            review_item_id=item.review_item_id,
            source_envelope_sha256=hashlib.sha256(
                (item.model_dump_json(indent=2) + "\n").encode("utf-8")
            ).hexdigest(),
            response_sha256=hashlib.sha256(
                response.model_dump_json().encode("utf-8")
            ).hexdigest(),
            previous_entry_sha256=previous,
        )
        result.append(entry)
        previous = hashlib.sha256(_canonical_bytes(entry)).hexdigest()
    return result


def build_ai_adjudication_promotion_bridge(
    *,
    root: Path,
    audit_manifest_path: Path,
    release_policy_path: Path,
    output_dir: Path,
) -> AIAdjudicationPromotionBridgeManifest:
    """Validate the source audit, then write its only valid promotion projection."""

    root = root.resolve()
    audit_manifest_path = audit_manifest_path.resolve()
    release_policy_path = release_policy_path.resolve()
    output_dir = output_dir.resolve()
    audit = validate_ai_adjudication_audit(
        root=root, manifest_path=audit_manifest_path
    )
    policy = SequentialReleasePolicy.model_validate_json(
        release_policy_path.read_text(encoding="utf-8")
    )
    if policy.release_mode != "sequential_one_item":
        raise ValueError("adjudication bridge requires sequential release policy")
    source_responses = _check_pin(
        root, audit.responses, label="AI adjudication responses"
    )
    responses = _projected_rows(
        responses_path=source_responses,
        reviewer_pseudonym=audit.reviewer_pseudonym,
    )
    if [row.review_item_id for row in responses] != audit.review_item_order:
        raise ValueError("adjudication projection order differs from validated audit")
    packet_path = _check_pin(root, audit.packet, label="adjudication packet")
    delivery = _delivery_rows(packet_path=packet_path, responses=responses)
    responses_path = output_dir / "promotion-responses.jsonl"
    delivery_path = output_dir / "promotion-delivery-audit.jsonl"
    metadata_path = output_dir / "promotion-metadata.json"
    bridge_path = output_dir / "promotion-bridge-manifest.json"
    _write_once(responses_path, _jsonl(responses))
    _write_once(delivery_path, _jsonl(delivery))
    metadata = ReviewArtifactMetadata(
        schema_version="1",
        review_role="adjudicator",
        reviewer_pseudonym=audit.reviewer_pseudonym,
        packet=audit.packet,
        release_policy=_pin(root, release_policy_path),
        responses=_pin(root, responses_path),
        sequential_delivery_audit=_pin(root, delivery_path),
        controlled_model_audit_manifest=None,
        expected_item_count=len(responses),
        delivery_mode="sequential_one_item",
        full_packet_distributed=False,
        canonical_source_map_distributed=False,
        prior_item_context_retained=False,
    )
    _write_once(
        metadata_path, (metadata.model_dump_json(indent=2) + "\n").encode("utf-8")
    )
    bridge = AIAdjudicationPromotionBridgeManifest(
        schema_version="1",
        finalized=True,
        projection="ai_adjudication_to_t6_promotion_v1",
        adjudication_audit_manifest=_pin(root, audit_manifest_path),
        adjudication_metadata=_pin(root, metadata_path),
        adjudication_responses=_pin(root, responses_path),
        sequential_delivery_audit=_pin(root, delivery_path),
        reviewer_pseudonym=audit.reviewer_pseudonym,
        item_count=len(responses),
        release_ordinal_order=audit.release_ordinal_order,
        review_item_order=audit.review_item_order,
    )
    _write_once(
        bridge_path, (bridge.model_dump_json(indent=2) + "\n").encode("utf-8")
    )
    validate_ai_adjudication_promotion_bridge(root=root, bridge_path=bridge_path)
    return bridge


def validate_ai_adjudication_promotion_bridge(
    *, root: Path, bridge_path: Path
) -> AIAdjudicationPromotionBridgeManifest:
    """Recompute the complete projection and reject any unbound promotion input."""

    bridge = AIAdjudicationPromotionBridgeManifest.model_validate_json(
        bridge_path.read_text(encoding="utf-8")
    )
    audit_path = _check_pin(
        root, bridge.adjudication_audit_manifest, label="adjudication audit manifest"
    )
    audit = validate_ai_adjudication_audit(root=root, manifest_path=audit_path)
    metadata_path = _check_pin(
        root, bridge.adjudication_metadata, label="adjudication metadata"
    )
    responses_path = _check_pin(
        root, bridge.adjudication_responses, label="projected adjudication responses"
    )
    delivery_path = _check_pin(
        root, bridge.sequential_delivery_audit, label="adjudication delivery audit"
    )
    metadata = ReviewArtifactMetadata.model_validate_json(
        metadata_path.read_text(encoding="utf-8")
    )
    source_responses = _check_pin(
        root, audit.responses, label="AI adjudication responses"
    )
    expected_responses = _projected_rows(
        responses_path=source_responses,
        reviewer_pseudonym=audit.reviewer_pseudonym,
    )
    packet_path = _check_pin(root, audit.packet, label="adjudication packet")
    expected_delivery = _delivery_rows(
        packet_path=packet_path, responses=expected_responses
    )
    if responses_path.read_bytes() != _jsonl(expected_responses):
        raise ValueError("projected adjudication responses differ from source audit")
    if delivery_path.read_bytes() != _jsonl(expected_delivery):
        raise ValueError("projected adjudication delivery differs from source audit")
    if (
        metadata.review_role != "adjudicator"
        or metadata.reviewer_pseudonym != audit.reviewer_pseudonym
        or metadata.packet != audit.packet
        or metadata.responses != bridge.adjudication_responses
        or metadata.sequential_delivery_audit != bridge.sequential_delivery_audit
        or metadata.expected_item_count != audit.item_count
        or bridge.reviewer_pseudonym != audit.reviewer_pseudonym
        or bridge.item_count != audit.item_count
        or bridge.release_ordinal_order != audit.release_ordinal_order
        or bridge.review_item_order != audit.review_item_order
    ):
        raise ValueError("adjudication bridge metadata differs from source audit")
    return bridge
