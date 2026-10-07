"""Promote only fresh stage-reviewed cases; patch validation remains pending."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import prepare_r2_stage_reviews as builder
import seal_r2_stage_review_session as sealer

ROOT = Path(__file__).resolve().parents[1]
C = builder.contracts
ROLES = builder.ROLES


def encoded(value):
    return builder.original.encoded(value)


def pin(out, name):
    return builder.pin_file(out, name)


def retained(responses, field):
    """Keep the ordered union; adjudication cannot erase a review obligation."""
    result = []
    for response in responses:
        for issue in getattr(response, field):
            if issue not in result:
                result.append(issue)
    return tuple(result)


def decision(responses):
    return all(r.decision == "include" and not r.pre_generation_blockers for r in responses)


def collect(root, out, protocol, history):
    protocol_pin = pin(out, "stage-review/review-protocol.json")
    tasks, sessions = set(history["task_ids"]), set(history["session_ids"])
    pending, bindings, accepted, records = {}, [], [], []
    for spec, case_pin, packet_pin in zip(
        history["specs"], protocol.case_inputs, protocol.inherited_issue_packets, strict=True
    ):
        packet = C.StageInheritedIssuePacket.model_validate_json(builder.read_pin(out, packet_pin))
        if packet != builder.inherited_packet(out, spec.case_id, history["records"]):
            raise ValueError("stage inherited packet omitted or changed historical concerns")
        captures, responses, rows = [], [], []
        for role in ROLES:
            capture_pin = pin(out, f"stage-review/reviews/{spec.case_id}/{role}/capture.json")
            cap, req, events, raw = sealer.validate_capture(
                out, capture_pin, protocol=protocol_pin, case_pin=case_pin, role=role
            )
            if events.task_id in tasks or events.session_id in sessions:
                raise ValueError("stage review reused a prior context")
            tasks.add(events.task_id)
            sessions.add(events.session_id)
            captures.append(capture_pin)
            responses.append(C.StageReviewResponse.model_validate_json(raw))
            rows.append((cap, req, events))
            records.append({"case_id": spec.case_id, "role": role, "capture": capture_pin.model_dump()})
        if rows[2][1].prior_responses != (rows[0][0].exact_final, rows[1][0].exact_final):
            raise ValueError("stage adjudication did not bind both fresh finals")
        if rows[2][2].started_at <= max(rows[0][2].completed_at, rows[1][2].completed_at):
            raise ValueError("stage adjudication preceded independent responses")
        disagreements = tuple(
            i for i, (a, b) in enumerate(zip(
                responses[0].inherited_issue_classifications,
                responses[1].inherited_issue_classifications, strict=True
            )) if a.category != b.category
        )
        if responses[2].classification_disagreements_resolved != disagreements:
            raise ValueError("adjudication did not explicitly resolve classification disagreements")
        evidence = C.StageReviewEvidence(
            case_id=spec.case_id, case_input=case_pin, protocol=protocol_pin,
            captures=tuple(captures), inherited_issues=packet_pin,
        )
        name = f"stage-review/evidence/{spec.case_id}.json"
        raw = encoded(evidence)
        evidence_pin = builder.MigrationEvidencePin(path=name, sha256=hashlib.sha256(raw).hexdigest())
        pending[out / name] = raw
        bindings.append(C.StageReviewDispositionEntry(case_id=spec.case_id, review_evidence=evidence_pin))
        if decision(responses):
            payload = spec.model_dump(mode="json")
            payload.pop("schema_version")
            accepted.append(C.StageCanonicalCase(
                **payload, review_protocol_sha256=protocol_pin.sha256,
                review_evidence_sha256=evidence_pin.sha256, review_evidence=evidence_pin,
                **{field: retained(responses, field) for field in C.CATEGORY_FIELDS[1:]},
            ))
    ids = tuple(case.case_id for case in accepted)
    excluded = tuple(s.case_id for s in history["specs"] if s.case_id not in ids)
    disposition = C.StageReviewDispositionManifest(
        protocol=protocol_pin, cases=tuple(bindings), accepted_case_ids=ids,
        excluded_case_ids=excluded, status="NOT_EVALUABLE" if not ids else
        "COMPLETE_WITH_EXCLUSIONS" if excluded else "COMPLETE_ALL_ACCEPTED",
    )
    pending[out / "stage-review/disposition.json"] = encoded(disposition)
    return pending, tuple(accepted), disposition, records


def promote(root=ROOT):
    root = Path(root).resolve()
    migration, out = root / "data/migration", root / "data/migration/ai-review"
    history = builder.audit_history(root, out)
    protocol = builder.prepare(root)
    if protocol.case_inputs != history["case_pins"]:
        raise ValueError("stage protocol changed the four revised inputs")
    pending, cases, disposition, records = collect(root, out, protocol, history)
    roster = ("\n".join(c.model_dump_json() for c in cases) + ("\n" if cases else "")).encode()
    for name in ("cases.jsonl", "oracle-assisted-roster.jsonl"):
        pending[migration / name] = roster
    pending[migration / "detector-led-roster.jsonl"] = b""
    ids = [case.case_id for case in cases]
    wave_map = {
        "schema_version": "r2-migration-wave-map-v1", "generation_cap": 6,
        "validation_cap": 8, "generation_waves": builder.promoter.OLD.waves(ids, 6, 3),
        "validation_waves": builder.promoter.OLD.waves(ids, 8, 7),
        "skipped_generation_sections": ["R2.4", "R2.5", "R2.6"], "provider_calls": 0,
    }
    pending[migration / "wave-map.json"] = encoded(wave_map)

    def planned(path):
        return {"path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(pending[path]).hexdigest()}

    def rooted(name):
        p = pin(out, name)
        return {"path": "data/migration/ai-review/" + p.path, "sha256": p.sha256}

    original_protocol = builder.AIReviewProtocol.model_validate_json((out / "review-protocol.json").read_bytes())
    original_ids = tuple(builder.AICaseSpec.model_validate_json(builder.read_pin(out, p)).case_id
                         for p in original_protocol.case_inputs)
    manifest = {
        "schema_version": "r2-stage-reviewed-roster-manifest-v1", "status": disposition.status,
        "configuration": 4, "detector_status": "NOT_EVALUABLE", "nonhuman": True,
        "review_provenance": protocol.review_provenance, "acceptance_policy": protocol.acceptance_policy,
        "source_intake": history["intake"], "review_evidence_root": "data/migration/ai-review",
        "original_review_receipt": rooted("original-review-receipt.json"),
        "revision_review_receipt": rooted("revisions/review-receipt.json"),
        "review_protocol": rooted("stage-review/review-protocol.json"),
        "stage_authorization": rooted("stage-review/authorization.json"),
        "runtime_snapshot_manifest": rooted("stage-review/runtime-source-manifest.json"),
        "revised_original_baseline_qualification": rooted("revisions/revised-original-baseline-qualification.json"),
        "disposition": planned(out / "stage-review/disposition.json"),
        "canonical_roster": planned(migration / "cases.jsonl"),
        "oracle_assisted_roster": planned(migration / "oracle-assisted-roster.jsonl"),
        "detector_led_roster": planned(migration / "detector-led-roster.jsonl"),
        "wave_map": planned(migration / "wave-map.json"),
        "original_candidate_count": 12, "historical_review_capture_count": 48,
        "stage_review_capture_count": len(records), "stage_case_ids": list(builder.CASE_IDS),
        "accepted_case_ids": ids, "excluded_case_ids": [i for i in original_ids if i not in ids],
        "stage_excluded_case_ids": list(disposition.excluded_case_ids),
        "generation_denominators": {"detector_led": 0, "oracle_assisted": len(ids), "combined": len(ids)},
        "distinct_accepted_source_bundles": len({c.source_bundle_group for c in cases}),
        "candidate_accounting": [{"case_id": i, "generation_eligible": i in ids,
            "stage_disposition": "accepted" if i in ids else "excluded" if i in builder.CASE_IDS else "not_revised",
            "original_v1_generation_eligible": False} for i in original_ids],
        "mandatory_validation_obligations": list(C.MANDATORY_VALIDATION),
        "reporting_limitations": list(C.REPORT_LIMITATIONS),
        "provider_calls": 0, "generation_authorized": False,
        "generation_remaining_gate": "R2.2 frozen Luna/max requests and separate sealed qualification",
    }
    pending[migration / "roster-manifest.json"] = encoded(manifest)
    pending[out / "stage-review/review-receipt.json"] = encoded({
        "schema_version": "migration-stage-review-terminal-receipt-v1", "status": "COMPLETE",
        "capture_count": len(records), "reviews": records,
        "historical_captures_retained": 48, "total_official_review_captures": 48 + len(records),
        "accepted_case_ids": ids, "excluded_case_ids": list(disposition.excluded_case_ids),
        "generation_calls": 0, "review_protocol": pin(out, "stage-review/review-protocol.json").model_dump(),
    })
    for path, raw in pending.items():
        if path.exists() and path.read_bytes() != raw:
            raise ValueError(f"immutable promotion artifact differs: {path}")
    # Replay the entire fresh disposition, including excluded chains, before publication.
    with tempfile.TemporaryDirectory(prefix="r2-stage-promotion-") as directory:
        stage = Path(directory)
        shutil.copytree(out, stage / "ai-review")
        for path, raw in pending.items():
            if path.is_relative_to(out):
                dest = stage / "ai-review" / path.relative_to(out)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
        (stage / "cases.jsonl").write_bytes(roster)
        loaded = C.load_stage_canonical_roster(
            stage / "cases.jsonl", review_evidence_root=stage / "ai-review",
            protocol_path=stage / "ai-review/stage-review/review-protocol.json",
            disposition_path=stage / "ai-review/stage-review/disposition.json",
        )
        if loaded != cases:
            raise ValueError("stage canonical replay differs")
    for path, raw in pending.items():
        builder.original.immutable_bytes(path, raw)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(promote(args.root), sort_keys=True, indent=2))
