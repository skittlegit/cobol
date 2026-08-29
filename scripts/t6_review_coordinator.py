"""Sequential, non-UI coordinator for one blinded T6-v2 review pass.

The reviewer workspace contains at most one source envelope. Completed source
envelopes are deleted after their response is validated; the full coordinator
queue and canonical source map are never copied into the workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    ReviewArtifactMetadata,
    SequentialDeliveryAuditEntry,
    validate_blinded_review_record,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    AIPrimaryReviewPolicy,
    ArtifactPin,
    BlindedReviewItem,
    artifact_sha256_matches,
    load_blinded_review_packet,
    load_sequential_release_policy,
    load_t6_v2_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/benchmark/t6-v2/manifest.json"
STATE_NAME = "coordinator-state.json"
CURRENT_NAME = "current-item.json"
RESPONSES_NAME = "responses.jsonl"
DELIVERY_AUDIT_NAME = "sequential-delivery-audit.jsonl"


class CoordinatorState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    review_role: Literal["ai_primary", "independent_verifier"]
    reviewer_pseudonym: str = Field(min_length=1)
    packet: ArtifactPin
    release_policy: ArtifactPin
    ai_primary_review_policy: ArtifactPin
    next_ordinal: int = Field(ge=1, le=23)
    completed_ids: list[str]
    current_item_id: str | None
    finalized: bool


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("coordinator artifacts must remain inside repository root")
    return resolved.relative_to(resolved_root).as_posix()


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _canonical_sha(model: BaseModel) -> str:
    payload = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_state(workspace: Path) -> CoordinatorState:
    return CoordinatorState.model_validate_json(
        (workspace / STATE_NAME).read_text(encoding="utf-8")
    )


def _write_state(workspace: Path, state: CoordinatorState) -> None:
    _atomic_write(workspace / STATE_NAME, state.model_dump_json(indent=2) + "\n")


def _load_pinned_queue(
    *, root: Path, state: CoordinatorState
) -> list[BlindedReviewItem]:
    packet_path = (root / state.packet.path).resolve()
    policy_path = (root / state.release_policy.path).resolve()
    if not artifact_sha256_matches(packet_path, state.packet.sha256):
        raise ValueError("blinded queue changed after coordinator initialization")
    if not artifact_sha256_matches(policy_path, state.release_policy.sha256):
        raise ValueError("release policy changed after coordinator initialization")
    policy = load_sequential_release_policy(policy_path)
    if policy.max_active_items != 1 or not policy.full_packet_distribution_prohibited:
        raise ValueError("release policy no longer enforces one-item delivery")
    return load_blinded_review_packet(packet_path)


def initialize(
    *,
    root: Path,
    manifest_path: Path,
    workspace: Path,
    reviewer_pseudonym: str,
    review_role: Literal["ai_primary", "independent_verifier"],
) -> CoordinatorState:
    """Create an empty reviewer workspace; no source item is released yet."""

    if workspace.exists():
        raise ValueError("review workspace already exists; refusing to overwrite")
    manifest = load_t6_v2_manifest(manifest_path)
    packet_path = (root / manifest.blinded_review_packet.path).resolve()
    policy_path = (root / manifest.blind_release_policy.path).resolve()
    if not artifact_sha256_matches(packet_path, manifest.blinded_review_packet.sha256):
        raise ValueError("manifest packet pin changed")
    if not artifact_sha256_matches(policy_path, manifest.blind_release_policy.sha256):
        raise ValueError("manifest release-policy pin changed")
    ai_policy = manifest.ai_primary_review_policy
    policy_path = (root / ai_policy.path).resolve()
    if not artifact_sha256_matches(policy_path, ai_policy.sha256):
        raise ValueError("AI-primary review policy pin changed")
    AIPrimaryReviewPolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
    workspace.mkdir(parents=True)
    state = CoordinatorState(
        schema_version="1",
        review_role=review_role,
        reviewer_pseudonym=reviewer_pseudonym,
        packet=manifest.blinded_review_packet,
        release_policy=manifest.blind_release_policy,
        ai_primary_review_policy=ai_policy,
        next_ordinal=1,
        completed_ids=[],
        current_item_id=None,
        finalized=False,
    )
    _write_state(workspace, state)
    return state


def release_next(*, root: Path, workspace: Path) -> BlindedReviewItem:
    """Release exactly the next envelope, refusing a second active source."""

    state = _load_state(workspace)
    current_path = workspace / CURRENT_NAME
    if state.finalized:
        raise ValueError("review pass is already finalized")
    if state.current_item_id is not None or current_path.exists():
        raise ValueError("one review item is already active")
    if state.next_ordinal > 22:
        raise ValueError("all 22 items are complete; run finalize")
    queue = _load_pinned_queue(root=root, state=state)
    matches = [item for item in queue if item.release_ordinal == state.next_ordinal]
    if len(matches) != 1:
        raise ValueError("release queue does not contain one exact next item")
    item = matches[0]
    if item.review_item_id in state.completed_ids:
        raise ValueError("release queue attempted to repeat a completed item")
    _atomic_write(current_path, item.model_dump_json(indent=2) + "\n")
    _write_state(
        state=state.model_copy(update={"current_item_id": item.review_item_id}),
        workspace=workspace,
    )
    return item


def record_response(
    *, root: Path, workspace: Path, response_path: Path
) -> BlindedReviewRecord:
    """Validate one response, append it, and remove the active source envelope."""

    state = _load_state(workspace)
    current_path = workspace / CURRENT_NAME
    if state.current_item_id is None or not current_path.is_file():
        raise ValueError("there is no active review item")
    item = BlindedReviewItem.model_validate_json(
        current_path.read_text(encoding="utf-8")
    )
    record = BlindedReviewRecord.model_validate_json(
        response_path.read_text(encoding="utf-8")
    )
    if record.reviewer_pseudonym != state.reviewer_pseudonym:
        raise ValueError("response reviewer differs from coordinator state")
    validate_blinded_review_record(record=record, item=item)
    responses_path = workspace / RESPONSES_NAME
    existing = []
    if responses_path.is_file():
        existing = [
            BlindedReviewRecord.model_validate_json(line)
            for line in responses_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if record.review_item_id in {row.review_item_id for row in existing}:
        raise ValueError("response artifact already contains this review item")
    _atomic_write(
        responses_path,
        "".join(row.model_dump_json() + "\n" for row in [*existing, record]),
    )
    audit_path = workspace / DELIVERY_AUDIT_NAME
    prior_audit = (
        [
            SequentialDeliveryAuditEntry.model_validate_json(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if audit_path.is_file()
        else []
    )
    if len(prior_audit) != state.next_ordinal - 1:
        raise ValueError("sequential delivery audit differs from coordinator state")
    audit_entry = SequentialDeliveryAuditEntry(
        schema_version="1",
        release_ordinal=item.release_ordinal,
        review_item_id=item.review_item_id,
        source_envelope_sha256=_sha(current_path),
        response_sha256=hashlib.sha256(
            record.model_dump_json().encode("utf-8")
        ).hexdigest(),
        previous_entry_sha256=(
            _canonical_sha(prior_audit[-1]) if prior_audit else None
        ),
    )
    _atomic_write(
        audit_path,
        "".join(row.model_dump_json() + "\n" for row in [*prior_audit, audit_entry]),
    )
    current_path.unlink()
    completed = [*state.completed_ids, record.review_item_id]
    _write_state(
        workspace,
        state.model_copy(
            update={
                "completed_ids": completed,
                "current_item_id": None,
                "next_ordinal": state.next_ordinal + 1,
            }
        ),
    )
    return record


def finalize(
    *,
    root: Path,
    workspace: Path,
    metadata_path: Path,
    controlled_model_audit_manifest: ArtifactPin | None = None,
    independent_verifier_audit_manifest: ArtifactPin | None = None,
) -> ArtifactPin:
    """Freeze a complete pass metadata file; external identity proof stays separate."""

    state = _load_state(workspace)
    if state.finalized:
        raise ValueError("review pass is already finalized")
    if state.current_item_id is not None or (workspace / CURRENT_NAME).exists():
        raise ValueError("cannot finalize while a source envelope is active")
    responses_path = workspace / RESPONSES_NAME
    rows = [
        BlindedReviewRecord.model_validate_json(line)
        for line in responses_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [row.review_item_id for row in rows]
    if len(rows) != 22 or len(set(ids)) != 22 or ids != state.completed_ids:
        raise ValueError("finalization requires 22 unique sequential responses")
    audit_path = workspace / DELIVERY_AUDIT_NAME
    audit_rows = [
        SequentialDeliveryAuditEntry.model_validate_json(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if (
        len(audit_rows) != 22
        or [row.release_ordinal for row in audit_rows] != list(range(1, 23))
        or [row.review_item_id for row in audit_rows] != ids
    ):
        raise ValueError("finalization requires an exact 22-item delivery audit")
    audit_manifest = (
        controlled_model_audit_manifest or independent_verifier_audit_manifest
    )
    if audit_manifest is None:
        raise ValueError("controlled-model finalization requires an aggregate audit")
    metadata = ReviewArtifactMetadata(
        schema_version="1",
        review_role=state.review_role,
        reviewer_pseudonym=state.reviewer_pseudonym,
        packet=state.packet,
        release_policy=state.release_policy,
        responses=ArtifactPin(
            path=_relative(root, responses_path), sha256=_sha(responses_path)
        ),
        sequential_delivery_audit=ArtifactPin(
            path=_relative(root, audit_path), sha256=_sha(audit_path)
        ),
        controlled_model_audit_manifest=audit_manifest,
        expected_item_count=22,
        delivery_mode="sequential_one_item",
        full_packet_distributed=False,
        canonical_source_map_distributed=False,
        prior_item_context_retained=False,
    )
    _atomic_write(metadata_path, metadata.model_dump_json(indent=2) + "\n")
    _write_state(workspace, state.model_copy(update={"finalized": True}))
    return ArtifactPin(path=_relative(root, metadata_path), sha256=_sha(metadata_path))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    init.add_argument("--workspace", type=Path, required=True)
    init.add_argument("--reviewer", required=True)
    init.add_argument(
        "--role",
        choices=("ai_primary", "independent_verifier"),
        default="ai_primary",
    )
    release = sub.add_parser("release")
    release.add_argument("--workspace", type=Path, required=True)
    record = sub.add_parser("record")
    record.add_argument("--workspace", type=Path, required=True)
    record.add_argument("--response", type=Path, required=True)
    finish = sub.add_parser("finalize")
    finish.add_argument("--workspace", type=Path, required=True)
    finish.add_argument("--metadata", type=Path, required=True)
    finish.add_argument("--controlled-model-audit", type=Path, required=True)
    status = sub.add_parser("status")
    status.add_argument("--workspace", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    if args.command == "init":
        result: object = initialize(
            root=root,
            manifest_path=args.manifest,
            workspace=args.workspace,
            reviewer_pseudonym=args.reviewer,
            review_role=args.role,
        )
    elif args.command == "release":
        result = release_next(root=root, workspace=args.workspace)
    elif args.command == "record":
        result = record_response(
            root=root, workspace=args.workspace, response_path=args.response
        )
    elif args.command == "finalize":
        result = finalize(
            root=root,
            workspace=args.workspace,
            metadata_path=args.metadata,
            controlled_model_audit_manifest=(
                ArtifactPin(
                    path=_relative(root, args.controlled_model_audit),
                    sha256=_sha(args.controlled_model_audit),
                )
                if args.controlled_model_audit is not None
                else None
            ),
        )
    else:
        result = _load_state(args.workspace)
    if isinstance(result, BaseModel):
        print(result.model_dump_json(indent=2))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
