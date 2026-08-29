"""Finalize T6-v2 from the sealed two-pass review and adjudication chain."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from cobol_archaeologist.benchmark.t6_adjudication import (
    validate_ai_adjudication_audit,
)
from cobol_archaeologist.benchmark.t6_adjudication_bridge import (
    validate_ai_adjudication_promotion_bridge,
)
from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    CollaborationSubagentResponseRecord,
    PinnedReviewMetadata,
    ReviewArtifactMetadata,
    ReviewEvidencePins,
    SequentialDeliveryAuditEntry,
    build_t6_review_promotion,
    propose_t6_finalized_manifest,
    validate_collaboration_subagent_audit,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    load_blinded_review_packet,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("T6 finalization artifact escapes the repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=_sha(resolved)
    )


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"refusing to overwrite frozen T6 artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _canonical_bytes(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _project_collaboration_pass(
    *, root: Path, audit_path: Path, expected_role: str
) -> tuple[object, bytes, bytes]:
    audit = validate_collaboration_subagent_audit(
        root=root, manifest_path=audit_path
    )
    if audit.review_role != expected_role:
        raise ValueError(f"sealed audit does not declare {expected_role}")
    packet = load_blinded_review_packet(root / audit.packet.path)
    raw_responses = [
        CollaborationSubagentResponseRecord.model_validate_json(raw)
        for raw in (root / audit.responses.path)
        .read_text(encoding="utf-8")
        .splitlines()
        if raw.strip()
    ]
    records: list[BlindedReviewRecord] = []
    delivery: list[SequentialDeliveryAuditEntry] = []
    previous: str | None = None
    for item, response in zip(packet, raw_responses, strict=True):
        record = BlindedReviewRecord(
            review_item_id=item.review_item_id,
            reviewer_pseudonym=audit.reviewer_pseudonym,
            completed_at="1970-01-01T00:00:00Z",
            review_response=response.review_response,
        )
        records.append(record)
        delivery_row = SequentialDeliveryAuditEntry(
            schema_version="1",
            release_ordinal=item.release_ordinal,
            review_item_id=item.review_item_id,
            source_envelope_sha256=hashlib.sha256(
                (item.model_dump_json(indent=2) + "\n").encode("utf-8")
            ).hexdigest(),
            response_sha256=hashlib.sha256(
                record.model_dump_json().encode("utf-8")
            ).hexdigest(),
            previous_entry_sha256=previous,
        )
        delivery.append(delivery_row)
        previous = hashlib.sha256(_canonical_bytes(delivery_row)).hexdigest()
    return (
        audit,
        "".join(record.model_dump_json() + "\n" for record in records).encode(
            "utf-8"
        ),
        "".join(row.model_dump_json() + "\n" for row in delivery).encode(
            "utf-8"
        ),
    )


def _metadata_bytes(
    *,
    root: Path,
    audit_path: Path,
    expected_role: str,
    responses_path: Path,
    delivery_path: Path,
) -> bytes:
    audit = validate_collaboration_subagent_audit(
        root=root, manifest_path=audit_path
    )
    if audit.review_role != expected_role:
        raise ValueError(f"sealed audit does not declare {expected_role}")
    metadata = ReviewArtifactMetadata(
        schema_version="1",
        review_role=audit.review_role,
        reviewer_pseudonym=audit.reviewer_pseudonym,
        packet=audit.packet,
        release_policy=audit.release_policy,
        responses=_pin(root, responses_path),
        sequential_delivery_audit=_pin(root, delivery_path),
        controlled_model_audit_manifest=_pin(root, audit_path),
        expected_item_count=22,
        delivery_mode="sequential_one_item",
        full_packet_distributed=False,
        canonical_source_map_distributed=False,
        prior_item_context_retained=False,
    )
    return (metadata.model_dump_json(indent=2) + "\n").encode("utf-8")


def promote(*, root: Path, output_dir: Path) -> Path:
    root = root.resolve()
    output_dir = output_dir.resolve()
    preparation = root / "data/benchmark/t6-v2/manifest.json"
    primary_audit = (
        root
        / "data/benchmark/t6-v2/review/ai-primary-collaboration/audit-manifest.json"
    )
    verifier_audit = (
        root
        / "data/benchmark/t6-v2/review/evidence/"
        "luna-independent-collaboration-subagent/audit-manifest.json"
    )
    adjudication_audit = (
        root
        / "data/benchmark/t6-v2/review/evidence/"
        "ai-adjudicator-collaboration-subagent/audit-manifest.json"
    )
    bridge_path = (
        root
        / "data/benchmark/t6-v2/review/evidence/"
        "ai-adjudicator-promotion-bridge/promotion-bridge-manifest.json"
    )
    correction_bridge_path = (
        root
        / "data/benchmark/t6-v2/review/evidence/"
        "pair-aware-ai-correction/promotion-bridge-manifest.json"
    )
    replacement_bridge_path = (
        root
        / "data/benchmark/t6-v2/replacements/evidence/final-multibatch/"
        "promotion-bridge-manifest.json"
    )

    # Validate the complete sealed chain before producing any projection.
    primary_audit_record, primary_responses, primary_delivery = (
        _project_collaboration_pass(
            root=root, audit_path=primary_audit, expected_role="ai_primary"
        )
    )
    verifier_audit_record, verifier_responses, verifier_delivery = (
        _project_collaboration_pass(
            root=root,
            audit_path=verifier_audit,
            expected_role="independent_verifier",
        )
    )
    validate_ai_adjudication_audit(
        root=root, manifest_path=adjudication_audit
    )
    bridge = validate_ai_adjudication_promotion_bridge(
        root=root, bridge_path=bridge_path
    )

    primary_responses_path = output_dir / "ai-primary-responses.jsonl"
    primary_delivery_path = output_dir / "ai-primary-delivery-audit.jsonl"
    verifier_responses_path = output_dir / "independent-verifier-responses.jsonl"
    verifier_delivery_path = output_dir / "independent-verifier-delivery-audit.jsonl"
    _write_once(primary_responses_path, primary_responses)
    _write_once(primary_delivery_path, primary_delivery)
    _write_once(verifier_responses_path, verifier_responses)
    _write_once(verifier_delivery_path, verifier_delivery)
    if primary_audit_record.review_item_order != verifier_audit_record.review_item_order:
        raise ValueError("controlled review passes cover different item orders")
    primary_metadata = _metadata_bytes(
        root=root,
        audit_path=primary_audit,
        expected_role="ai_primary",
        responses_path=primary_responses_path,
        delivery_path=primary_delivery_path,
    )
    verifier_metadata = _metadata_bytes(
        root=root,
        audit_path=verifier_audit,
        expected_role="independent_verifier",
        responses_path=verifier_responses_path,
        delivery_path=verifier_delivery_path,
    )
    primary_metadata_path = output_dir / "ai-primary-promotion-metadata.json"
    verifier_metadata_path = output_dir / "independent-verifier-promotion-metadata.json"
    _write_once(primary_metadata_path, primary_metadata)
    _write_once(verifier_metadata_path, verifier_metadata)
    evidence = ReviewEvidencePins(
        ai_primary=PinnedReviewMetadata(**_pin(root, primary_metadata_path).model_dump()),
        independent_verifier=PinnedReviewMetadata(
            **_pin(root, verifier_metadata_path).model_dump()
        ),
        adjudication=PinnedReviewMetadata(
            **bridge.adjudication_metadata.model_dump()
        ),
        ai_adjudication_bridge_manifest=_pin(root, bridge_path),
        pair_correction_bridge_manifest=(
            _pin(root, correction_bridge_path)
            if correction_bridge_path.is_file()
            else None
        ),
        replacement_bridge_manifest=(
            _pin(root, replacement_bridge_path)
            if replacement_bridge_path.is_file()
            else None
        ),
    )
    report = build_t6_review_promotion(
        root=root, manifest_path=preparation, evidence=evidence
    )
    if not report.evaluation_ready or report.gaps:
        failure_path = (
            root
            / "data/benchmark/t6-v2/review/evidence/promotion-gate/"
            "pre-pair-correction-report.json"
        )
        _write_once(
            failure_path,
            (report.model_dump_json(indent=2) + "\n").encode("utf-8"),
        )
        gap_text = ", ".join(
            f"{gap.code}:{gap.review_item_id or gap.pair_id or '-'}"
            for gap in report.gaps
        )
        raise ValueError(f"T6 promotion gate is not ready: {gap_text}")

    rows_path = output_dir / "evaluation-rows.jsonl"
    rows = [*report.carried_instances, *report.candidate_instances]
    rows_payload = "".join(row.model_dump_json() + "\n" for row in rows).encode(
        "utf-8"
    )
    _write_once(rows_path, rows_payload)
    report_path = output_dir / "promotion-report.json"
    _write_once(report_path, (report.model_dump_json(indent=2) + "\n").encode("utf-8"))
    finalized = propose_t6_finalized_manifest(
        root=root,
        report=report,
        promotion_report=_pin(root, report_path),
        evaluation_rows=_pin(root, rows_path),
    )
    finalized_path = output_dir / "manifest.json"
    _write_once(
        finalized_path,
        (finalized.model_dump_json(indent=2) + "\n").encode("utf-8"),
    )
    return finalized_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/benchmark/t6-v2/final"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir.is_absolute()
        else (root / args.output_dir).resolve()
    )
    print(promote(root=root, output_dir=output_dir))


if __name__ == "__main__":
    main()
