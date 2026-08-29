from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    PinnedReviewMetadata,
    ReviewEvidencePins,
    ReviewResponse,
    SequentialDeliveryAuditEntry,
    T6ReviewPromotionReport,
    _hash_matches,
    build_controlled_review_prompt,
    build_t6_review_promotion,
    propose_t6_finalized_manifest,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin, BlindedReviewItem
from cobol_archaeologist.eval.codex_batch import strict_codex_schema
from cobol_archaeologist.eval.config3_live import (
    canonical_sha256,
    expected_codex_request_sha256,
    load_finalized_t6_rows,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data/benchmark/t6-v2/manifest.json"
PACKET_PATH = ROOT / "data/benchmark/t6-v2/review/packet.jsonl"
RELEASE_POLICY_PATH = ROOT / "data/benchmark/t6-v2/review/release-policy.json"
PROPOSAL_PATH = ROOT / "data/benchmark/t6-v2/candidates/pair_proposals.jsonl"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def test_review_pin_accepts_lf_checkout_of_legacy_crlf_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "packet.jsonl"
    artifact.write_bytes(b'{"review_item_id":"rvw-1"}\n')
    legacy_crlf = artifact.read_bytes().replace(b"\n", b"\r\n")

    assert _hash_matches(artifact, hashlib.sha256(legacy_crlf).hexdigest())
    assert not _hash_matches(artifact, hashlib.sha256(b"changed\r\n").hexdigest())


def _proposal_labels() -> dict[str, tuple[str, list[dict[str, object]]]]:
    result: dict[str, tuple[str, list[dict[str, object]]]] = {}
    for raw in PROPOSAL_PATH.read_text(encoding="utf-8").splitlines():
        pair = json.loads(raw)
        for side in pair["sides"]:
            result[side["blind_review_id"]] = (
                side["proposed_drift_type"],
                side["proposed_labels"]["line_level"],
            )
    return result


def _responses(reviewer: str) -> list[dict[str, object]]:
    proposals = _proposal_labels()
    rows = []
    for raw in PACKET_PATH.read_text(encoding="utf-8").splitlines():
        item = json.loads(raw)
        drift_type, citations = proposals[item["review_item_id"]]
        blind_citations = [
            {
                "program": citation["program"],
                "line": citation["line"],
                "source_alias": item["source_alias"],
            }
            for citation in citations
        ]
        rows.append(
            {
                "review_item_id": item["review_item_id"],
                "reviewer_pseudonym": reviewer,
                "completed_at": "2026-08-24T12:00:00Z",
                "review_response": {
                    "decision": "include",
                    "drift_type": drift_type,
                    "line_level": blind_citations,
                    "rationale": "Independent source and visible-code review supports this label.",
                    "uncertainty_notes": None,
                },
            }
        )
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _pin(path: Path) -> dict[str, str]:
    return {"path": _relative(path), "sha256": _sha(path)}


def _write_delivery_audit(path: Path, rows: list[dict[str, object]]) -> ArtifactPin:
    packet = {
        item.review_item_id: item
        for raw in PACKET_PATH.read_text(encoding="utf-8").splitlines()
        for item in [BlindedReviewItem.model_validate_json(raw)]
    }
    entries: list[SequentialDeliveryAuditEntry] = []
    previous = None
    for row in rows:
        ordinal = packet[str(row["review_item_id"])].release_ordinal
        entry = SequentialDeliveryAuditEntry(
            schema_version="1",
            release_ordinal=ordinal,
            review_item_id=str(row["review_item_id"]),
            source_envelope_sha256=hashlib.sha256(
                (
                    packet[str(row["review_item_id"])].model_dump_json(indent=2) + "\n"
                ).encode()
            ).hexdigest(),
            response_sha256=hashlib.sha256(
                BlindedReviewRecord.model_validate(row).model_dump_json().encode()
            ).hexdigest(),
            previous_entry_sha256=previous,
        )
        entries.append(entry)
        previous = hashlib.sha256(
            json.dumps(
                entry.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    _write_jsonl(path, [entry.model_dump(mode="json") for entry in entries])
    return ArtifactPin(**_pin(path))


def _write_verifier_audit(
    *,
    tmp_path: Path,
    reviewer: str,
    rows: list[dict[str, object]],
    responses: ArtifactPin,
    delivery: ArtifactPin,
    tamper_identity_authority: bool = False,
    review_role: str = "independent_verifier",
) -> ArtifactPin:
    model_id = "gpt-5.6-sol" if review_role == "ai_primary" else "gpt-5.6-luna"
    packet = [json.loads(raw) for raw in PACKET_PATH.read_text().splitlines()]
    items = []
    for item, row in zip(packet, rows, strict=True):
        ordinal = item["release_ordinal"]
        blinded_item = BlindedReviewItem.model_validate(item)
        prompt = build_controlled_review_prompt(
            blinded_item, attempt=1, review_role=review_role
        )
        schema = strict_codex_schema(ReviewResponse)
        request_hash = expected_codex_request_sha256(
            prompt=prompt,
            schema=schema,
            sources={},
            transport="native",
            codex_binary="codex.exe",
            runtime_source_sha256="e" * 64,
            chatgpt_account_sha256="b" * 64,
            authorized_hunts=(),
        )
        identity_path = tmp_path / f"{review_role}-identity-{ordinal:02d}.json"
        identity = {
            "schema_version": "1",
            "review_role": review_role,
            "review_item_id": item["review_item_id"],
            "release_ordinal": ordinal,
            "attempt": 1,
            "source_alias": item["source_alias"],
            "source_text_sha256": hashlib.sha256(
                item["source_text"].encode()
            ).hexdigest(),
            "authority_sha256": canonical_sha256(blinded_item.authority),
            "packet": {"path": _relative(PACKET_PATH), "sha256": _sha(PACKET_PATH)},
            "release_policy": {
                "path": _relative(RELEASE_POLICY_PATH),
                "sha256": _sha(RELEASE_POLICY_PATH),
            },
            "provider": "chatgpt-codex",
            "authentication": "ChatGPT",
            "authentication_identity_sha256": "b" * 64,
            "model_id": model_id,
            "reasoning_effort": "max",
            "transport": "native",
            "codex_binary": "codex.exe",
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "schema_sha256": canonical_sha256(schema),
            "runtime_source_sha256": "e" * 64,
            "expected_request_sha256": request_hash,
            "visible_review_items": 1,
            "staged_source_bundles": 0,
            "tools_authorized": 0,
            "prior_item_context_included": False,
        }
        if tamper_identity_authority and ordinal == 1:
            identity["authority_sha256"] = "0" * 64
        identity_path.write_text(json.dumps(identity), encoding="utf-8")
        raw_dir = tmp_path / "raw" / request_hash
        raw_dir.mkdir(parents=True)
        execution_path = raw_dir / "execution.json"
        execution_path.write_text(
            json.dumps(
                {
                    "request_sha256": request_hash,
                    "tool_logs": [],
                    "final_message": json.dumps(row["review_response"]),
                }
            ),
            encoding="utf-8",
        )
        marker_path = raw_dir / "complete"
        marker_path.write_text(
            json.dumps({"key": request_hash, "request_sha256": request_hash}),
            encoding="utf-8",
        )
        items.append(
            {
                "release_ordinal": ordinal,
                "review_item_id": item["review_item_id"],
                "attempts": [
                    {
                        "attempt": 1,
                        "request_identity": _pin(identity_path),
                        "raw_execution": _pin(execution_path),
                        "raw_completion_marker": _pin(marker_path),
                        "expected_request_sha256": request_hash,
                        "outcome": "accepted",
                        "invalid_marker": None,
                    }
                ],
            }
        )
    audit_path = tmp_path / f"{review_role.replace('_', '-')}-audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "finalized": True,
                "review_role": review_role,
                "reviewer_pseudonym": reviewer,
                "packet": {"path": _relative(PACKET_PATH), "sha256": _sha(PACKET_PATH)},
                "release_policy": {
                    "path": _relative(RELEASE_POLICY_PATH),
                    "sha256": _sha(RELEASE_POLICY_PATH),
                },
                "responses": responses.model_dump(mode="json"),
                "sequential_delivery_audit": delivery.model_dump(mode="json"),
                "provider": "chatgpt-codex",
                "authentication": "ChatGPT",
                "authentication_identity_sha256": "b" * 64,
                "model_id": model_id,
                "reasoning_effort": "max",
                "visible_review_items_per_call": 1,
                "staged_source_bundles_per_call": 0,
                "tools_authorized_per_call": 0,
                "prior_item_context_included": False,
                "item_count": 22,
                "release_ordinal_order": list(range(1, 23)),
                "review_item_order": [row["review_item_id"] for row in rows],
                "items": items,
            }
        ),
        encoding="utf-8",
    )
    return ArtifactPin(**_pin(audit_path))


def _write_metadata(
    *,
    tmp_path: Path,
    role: str,
    reviewer: str,
    rows: list[dict[str, object]],
    canonical_source_map_distributed: bool = False,
    tamper_verifier_identity_authority: bool = False,
    tamper_primary_identity_authority: bool = False,
) -> PinnedReviewMetadata:
    response_path = tmp_path / f"{role}-responses.jsonl"
    _write_jsonl(response_path, rows)
    response_pin = ArtifactPin(**_pin(response_path))
    delivery_pin = _write_delivery_audit(
        tmp_path / f"{role}-delivery-audit.jsonl", rows
    )
    controlled_audit = (
        _write_verifier_audit(
            tmp_path=tmp_path,
            reviewer=reviewer,
            rows=rows,
            responses=response_pin,
            delivery=delivery_pin,
            tamper_identity_authority=(
                tamper_primary_identity_authority
                if role == "ai_primary"
                else tamper_verifier_identity_authority
            ),
            review_role=role,
        )
        if role in {"ai_primary", "independent_verifier"} and len(rows) == 22
        else None
    )
    metadata_path = tmp_path / f"{role}-metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "review_role": role,
                "reviewer_pseudonym": reviewer,
                "packet": {"path": _relative(PACKET_PATH), "sha256": _sha(PACKET_PATH)},
                "release_policy": {
                    "path": _relative(RELEASE_POLICY_PATH),
                    "sha256": _sha(RELEASE_POLICY_PATH),
                },
                "responses": {
                    "path": _relative(response_path),
                    "sha256": _sha(response_path),
                },
                "sequential_delivery_audit": delivery_pin.model_dump(mode="json"),
                "controlled_model_audit_manifest": (
                    controlled_audit.model_dump(mode="json")
                    if controlled_audit is not None
                    else None
                ),
                "expected_item_count": len(rows),
                "delivery_mode": "sequential_one_item",
                "full_packet_distributed": False,
                "canonical_source_map_distributed": canonical_source_map_distributed,
                "prior_item_context_retained": False,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return PinnedReviewMetadata(
        path=_relative(metadata_path), sha256=_sha(metadata_path)
    )


def _evidence(
    tmp_path: Path,
    *,
    primary: list[dict[str, object]] | None = None,
    verifier: list[dict[str, object]] | None = None,
    primary_reviewer: str = "primary-a",
    verifier_reviewer: str = "verifier-b",
    adjudication: list[dict[str, object]] | None = None,
    tamper_verifier_identity_authority: bool = False,
    tamper_primary_identity_authority: bool = False,
) -> ReviewEvidencePins:
    primary = primary if primary is not None else _responses(primary_reviewer)
    verifier = verifier if verifier is not None else _responses(verifier_reviewer)
    adjudication_pin = None
    if adjudication is not None:
        adjudication_pin = _write_metadata(
            tmp_path=tmp_path,
            role="adjudicator",
            reviewer="adjudicator-c",
            rows=adjudication,
        )
    primary_pin = _write_metadata(
        tmp_path=tmp_path,
        role="ai_primary",
        reviewer=primary_reviewer,
        rows=primary,
        tamper_primary_identity_authority=tamper_primary_identity_authority,
    )
    return ReviewEvidencePins(
        ai_primary=primary_pin,
        independent_verifier=_write_metadata(
            tmp_path=tmp_path,
            role="independent_verifier",
            reviewer=verifier_reviewer,
            rows=verifier,
            tamper_verifier_identity_authority=(tamper_verifier_identity_authority),
        ),
        adjudication=adjudication_pin,
    )


def _build(evidence: ReviewEvidencePins):
    evidence_dir = (ROOT / evidence.ai_primary.path).parent
    manifest_path = evidence_dir / "manifest.json"
    return build_t6_review_promotion(
        root=ROOT,
        manifest_path=manifest_path if manifest_path.is_file() else MANIFEST_PATH,
        evidence=evidence,
    )


def test_incomplete_pass_fails_before_promotion(tmp_path: Path) -> None:
    primary = _responses("primary-a")[:-1]
    with pytest.raises(ValueError, match="audit manifest"):
        _build(_evidence(tmp_path, primary=primary))


def test_complete_pass_in_wrong_release_order_fails_closed(tmp_path: Path) -> None:
    primary = _responses("primary-a")
    primary[0], primary[1] = primary[1], primary[0]
    with pytest.raises(ValueError, match="release order"):
        _build(_evidence(tmp_path, primary=primary))


def test_same_reviewer_cannot_fill_both_roles(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be distinct"):
        _build(
            _evidence(
                tmp_path,
                primary_reviewer="same-reviewer",
                verifier_reviewer="same-reviewer",
            )
        )


def test_canonical_source_map_distribution_fails_closed(tmp_path: Path) -> None:
    primary = _responses("primary-a")
    verifier = _responses("verifier-b")
    compromised_primary = _write_metadata(
        tmp_path=tmp_path,
        role="ai_primary",
        reviewer="primary-a",
        rows=primary,
        canonical_source_map_distributed=True,
    )
    evidence = ReviewEvidencePins(
        ai_primary=compromised_primary,
        independent_verifier=_write_metadata(
            tmp_path=tmp_path,
            role="independent_verifier",
            reviewer="verifier-b",
            rows=verifier,
        ),
    )
    with pytest.raises(ValueError, match="canonical_source_map_distributed"):
        _build(evidence)


def test_compromised_luna_diagnostic_cannot_count_as_review(
    tmp_path: Path,
) -> None:
    diagnostic = (
        ROOT / "data/benchmark/t6-v2/diagnostics/compromised-packet-luna-max.meta.json"
    )
    evidence = _evidence(tmp_path)
    evidence = evidence.model_copy(
        update={
            "independent_verifier": PinnedReviewMetadata(
                path=_relative(diagnostic), sha256=_sha(diagnostic)
            )
        }
    )
    with pytest.raises(ValueError):
        _build(evidence)


def test_disputed_adjudication_requires_validated_ai_audit_bridge(
    tmp_path: Path,
) -> None:
    primary = _responses("primary-a")
    verifier = _responses("verifier-b")
    disputed_id = next(
        row["review_item_id"]
        for row in verifier
        if row["review_response"]["drift_type"] != "D7_conformant"
    )
    disputed = next(row for row in verifier if row["review_item_id"] == disputed_id)
    disputed["review_response"]["drift_type"] = "D3_contradictory"
    resolution = next(
        row.copy() for row in primary if row["review_item_id"] == disputed_id
    )
    resolution["reviewer_pseudonym"] = "adjudicator-c"

    with pytest.raises(ValueError, match="validated AI audit bridge"):
        _build(
            _evidence(
                tmp_path,
                primary=primary,
                verifier=verifier,
                adjudication=[resolution],
            )
        )


def test_missing_adjudication_fails_closed(tmp_path: Path) -> None:
    primary = _responses("primary-a")
    verifier = _responses("verifier-b")
    verifier[0]["review_response"]["decision"] = "needs_adjudication"
    with pytest.raises(ValueError, match="require.*adjudication"):
        _build(_evidence(tmp_path, primary=primary, verifier=verifier))


def test_reviewed_label_can_supersede_unreviewed_proposal(
    tmp_path: Path,
) -> None:
    primary = _responses("primary-a")
    verifier = _responses("verifier-b")
    target_id = next(
        row["review_item_id"]
        for row in primary
        if row["review_response"]["drift_type"] != "D7_conformant"
    )
    for rows in (primary, verifier):
        row = next(item for item in rows if item["review_item_id"] == target_id)
        row["review_response"]["drift_type"] = "D3_contradictory"

    report = _build(
        _evidence(
            tmp_path, primary=primary, verifier=verifier, adjudication=[]
        )
    )

    assert report.evaluation_ready
    assert report.evaluation_eligible_pair_count == 20
    assert not report.gaps
    reviewed = next(
        row for row in report.candidate_instances if row.drift_type == "D3_contradictory"
    )
    assert reviewed.provenance.source == "real_curated"


def test_tampered_ai_primary_request_identity_fails_closed(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path, tamper_primary_identity_authority=True)
    with pytest.raises(ValueError, match="request identity differs from frozen item"):
        _build(evidence)


def test_successful_review_promotes_20_pairs_and_40_sides(tmp_path: Path) -> None:
    report = _build(_evidence(tmp_path, adjudication=[]))

    assert report.evaluation_ready
    assert report.evaluation_eligible_pair_count == 20
    assert report.resolved_candidate_pairs == 11
    assert len(report.carried_instances) == 18
    assert len(report.candidate_instances) == 22
    assert len(report.proposed_instance_order) == 40
    assert report.proposed_candidate_instance_ids == [
        f"drift_{number:06d}" for number in range(120001, 120023)
    ]
    assert report.controlled_ai_primary_verified is True
    assert report.canonical_artifacts_written is False
    assert all(
        row.provenance.source == "real_curated" for row in report.candidate_instances
    )
    assert all(row.provenance.mutation is None for row in report.candidate_instances)
    assert set(report.proposed_source_inputs) == set(report.proposed_instance_order)
    rows_path = tmp_path / "evaluation-rows.jsonl"
    rows_path.write_text(
        "".join(
            row.model_dump_json() + "\n"
            for row in [*report.carried_instances, *report.candidate_instances]
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "promotion-report.json"
    report_path.write_text(report.model_dump_json(), encoding="utf-8")
    finalized = propose_t6_finalized_manifest(
        root=ROOT,
        report=report,
        promotion_report=ArtifactPin(
            path=_relative(report_path), sha256=_sha(report_path)
        ),
        evaluation_rows=ArtifactPin(
            path=_relative(rows_path),
            sha256=_sha(rows_path),
        ),
    )
    assert finalized.finalized
    assert finalized.evaluation_ready
    assert finalized.pair_order == report.proposed_pair_order
    assert finalized.instance_order == report.proposed_instance_order
    assert finalized.source_inputs == report.proposed_source_inputs
    assert finalized.pair_members == report.proposed_pair_members
    finalized_path = tmp_path / "finalized-manifest.json"
    finalized_path.write_text(finalized.model_dump_json(), encoding="utf-8")
    loaded_manifest, loaded_rows = load_finalized_t6_rows(
        root=ROOT, manifest_path=finalized_path
    )
    assert loaded_manifest.evaluation_side_count == 40
    assert [row.instance_id for row in loaded_rows] == report.proposed_instance_order


def test_missing_ai_primary_aggregate_audit_fails_closed(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path)
    path = ROOT / evidence.ai_primary.path
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["controlled_model_audit_manifest"] = None
    path.write_text(json.dumps(payload), encoding="utf-8")
    evidence = evidence.model_copy(
        update={"ai_primary": PinnedReviewMetadata(**_pin(path))}
    )
    with pytest.raises(ValueError, match="audit manifest"):
        _build(evidence)


def test_missing_verifier_aggregate_audit_fails_closed(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    metadata_path = ROOT / evidence.independent_verifier.path
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["controlled_model_audit_manifest"] = None
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    evidence = evidence.model_copy(
        update={"independent_verifier": PinnedReviewMetadata(**_pin(metadata_path))}
    )
    with pytest.raises(ValueError, match="audit manifest"):
        _build(evidence)


def test_promotion_recomputes_and_rejects_tampered_verifier_authority_hash(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path, tamper_verifier_identity_authority=True)
    with pytest.raises(ValueError, match="request identity differs from frozen item"):
        _build(evidence)


def test_promotion_rejects_repeated_pair_members(tmp_path: Path) -> None:
    report = _build(_evidence(tmp_path, adjudication=[]))
    payload = report.model_dump(mode="json")
    first_pair = payload["proposed_pair_order"][0]
    first_member = payload["proposed_pair_members"][first_pair][0]
    payload["proposed_pair_members"][first_pair] = [first_member, first_member]

    with pytest.raises(ValueError, match="two distinct"):
        T6ReviewPromotionReport.model_validate(payload)


def test_promotion_rejects_non_temporal_repeated_rows(tmp_path: Path) -> None:
    report = _build(_evidence(tmp_path, adjudication=[]))
    payload = report.model_dump(mode="json")
    payload["candidate_instances"][1]["regulation_clause"] = payload[
        "candidate_instances"
    ][0]["regulation_clause"]

    with pytest.raises(ValueError, match="distinct regulation versions"):
        T6ReviewPromotionReport.model_validate(payload)
