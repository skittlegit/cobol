"""Build byte-exact T6 collaboration-subagent evidence from a transcript JSONL."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.benchmark.t6_review import (
    CollaborationSubagentAttemptAudit,
    CollaborationSubagentAuditManifest,
    CollaborationSubagentItemAudit,
    CollaborationSubagentResponseRecord,
    ReviewResponse,
    SequentialDeliveryAuditEntry,
    validate_collaboration_subagent_audit,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin, load_blinded_review_packet


class TranscriptAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    task_identity: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    final_message: str = Field(min_length=1)
    outcome: Literal["schema_invalid", "accepted"]
    envelope_format: Literal["visible_canonical", "full_blind_packet_row"]
    envelope_separator: Literal["space", "lf"]


class TranscriptItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    attempts: list[TranscriptAttempt] = Field(min_length=1)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_path(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("audit artifacts must remain inside the repository root")
    return ArtifactPin(
        path=resolved_path.relative_to(resolved_root).as_posix(),
        sha256=_sha_path(resolved_path),
    )


def _canonical_bytes(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_jsonl(path: Path, rows: list[BaseModel]) -> None:
    path.write_text(
        "".join(f"{row.model_dump_json()}\n" for row in rows), encoding="utf-8"
    )


def build(args: argparse.Namespace) -> Path:
    root = args.root.resolve()
    packet_path = args.packet.resolve()
    release_policy_path = args.release_policy.resolve()
    response_schema_path = args.response_schema.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_rows = [
        TranscriptItem.model_validate_json(raw)
        for raw in args.transcript.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    packet = load_blinded_review_packet(packet_path)
    if len(packet) != 22 or len(transcript_rows) != 22:
        raise ValueError("packet and transcript must each contain exactly 22 items")
    model_id = (
        "gpt-5.6-sol" if args.review_role == "ai_primary" else "gpt-5.6-luna"
    )
    response_rows: list[CollaborationSubagentResponseRecord] = []
    delivery_rows: list[SequentialDeliveryAuditEntry] = []
    audit_items: list[CollaborationSubagentItemAudit] = []
    previous: str | None = None
    invalid_count = 0
    packet_lines = [
        raw
        for raw in packet_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    for item, packet_line, transcript in zip(
        packet, packet_lines, transcript_rows, strict=True
    ):
        if (
            transcript.release_ordinal != item.release_ordinal
            or transcript.review_item_id != item.review_item_id
        ):
            raise ValueError("transcript differs from frozen packet order")
        visible = {
            "review_item_id": item.review_item_id,
            "authority": item.authority.model_dump(mode="json"),
            "source_alias": item.source_alias,
            "source_text": item.source_text,
        }
        envelope = json.dumps(
            visible, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        attempts: list[CollaborationSubagentAttemptAudit] = []
        for source_attempt in transcript.attempts:
            prompt = source_attempt.prompt.encode("utf-8")
            final = source_attempt.final_message.encode("utf-8")
            attempt_envelope = (
                envelope
                if source_attempt.envelope_format == "visible_canonical"
                else packet_line.encode("utf-8")
            )
            separator = (
                b" " if source_attempt.envelope_separator == "space" else b"\n"
            )
            marker = b"Envelope:" + separator + attempt_envelope
            if prompt.count(b"Envelope:") != 1 or prompt.count(marker) != 1:
                raise ValueError("transcript prompt is not exactly one-item visible")
            attempt = CollaborationSubagentAttemptAudit(
                attempt=source_attempt.attempt,
                task_identity=source_attempt.task_identity,
                fork_turns="none",
                model_id=model_id,
                reasoning_effort="max",
                tools_authorized=0,
                prior_item_context_included=False,
                visible_review_items=1,
                staged_source_bundles=0,
                envelope_format=source_attempt.envelope_format,
                envelope_separator=source_attempt.envelope_separator,
                prompt_envelope_sha256=_sha_bytes(attempt_envelope),
                prompt_utf8_base64=base64.b64encode(prompt).decode("ascii"),
                prompt_utf8_length=len(prompt),
                prompt_sha256=_sha_bytes(prompt),
                final_message_utf8_base64=base64.b64encode(final).decode("ascii"),
                final_message_utf8_length=len(final),
                final_message_sha256=_sha_bytes(final),
                outcome=source_attempt.outcome,
            )
            invalid_count += attempt.outcome == "schema_invalid"
            attempts.append(attempt)
        accepted = attempts[-1]
        source_envelope_sha256 = accepted.prompt_envelope_sha256
        response = ReviewResponse.model_validate_json(
            base64.b64decode(accepted.final_message_utf8_base64, validate=True)
        )
        response_rows.append(
            CollaborationSubagentResponseRecord(
                schema_version="1",
                audit_variant="collaboration_subagent",
                release_ordinal=item.release_ordinal,
                review_item_id=item.review_item_id,
                task_identity=accepted.task_identity,
                attempt=accepted.attempt,
                review_response=response,
            )
        )
        audit_items.append(
            CollaborationSubagentItemAudit(
                release_ordinal=item.release_ordinal,
                review_item_id=item.review_item_id,
                source_alias=item.source_alias,
                source_envelope_sha256=source_envelope_sha256,
                attempts=attempts,
            )
        )
        delivery = SequentialDeliveryAuditEntry(
            schema_version="1",
            release_ordinal=item.release_ordinal,
            review_item_id=item.review_item_id,
            source_envelope_sha256=source_envelope_sha256,
            response_sha256=accepted.final_message_sha256,
            previous_entry_sha256=previous,
        )
        delivery_rows.append(delivery)
        previous = _sha_bytes(_canonical_bytes(delivery))
    responses_path = output_dir / "responses.jsonl"
    delivery_path = output_dir / "sequential-delivery-audit.jsonl"
    manifest_path = output_dir / "audit-manifest.json"
    _write_jsonl(responses_path, response_rows)
    _write_jsonl(delivery_path, delivery_rows)
    manifest = CollaborationSubagentAuditManifest(
        schema_version="1",
        audit_variant="collaboration_subagent",
        finalized=True,
        review_role=args.review_role,
        reviewer_pseudonym=args.reviewer_pseudonym,
        packet=_pin(root, packet_path),
        release_policy=_pin(root, release_policy_path),
        response_schema=_pin(root, response_schema_path),
        responses=_pin(root, responses_path),
        sequential_delivery_audit=_pin(root, delivery_path),
        provider="chatgpt-codex-collaboration",
        model_id=model_id,
        reasoning_effort="max",
        fork_turns_per_attempt="none",
        fresh_task_per_attempt=True,
        visible_review_items_per_call=1,
        staged_source_bundles_per_call=0,
        tools_authorized_per_call=0,
        prior_item_context_included=False,
        native_execution_bundle_claimed=False,
        item_count=22,
        accepted_count=22,
        schema_invalid_attempt_count=invalid_count,
        retry_count=invalid_count,
        release_ordinal_order=list(range(1, 23)),
        review_item_order=[item.review_item_id for item in packet],
        items=audit_items,
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    validate_collaboration_subagent_audit(root=root, manifest_path=manifest_path)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--release-policy", type=Path, required=True)
    parser.add_argument("--response-schema", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--review-role", choices=("ai_primary", "independent_verifier"), required=True
    )
    parser.add_argument("--reviewer-pseudonym", required=True)
    args = parser.parse_args()
    print(build(args))


if __name__ == "__main__":
    main()
