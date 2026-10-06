"""Promote only an exhaustively reconciled, nonhuman R2 review roster."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICanonicalMigrationCase,
    AICaseSpec,
    AIHostSessionEvents,
    AIReviewCapture,
    AIReviewDispositionManifest,
    AIReviewEvidence,
    AIReviewProtocol,
    AIReviewRequest,
    AIReviewResponse,
    _load_review_chain,
    _pinned,
    _ReviewCaseBinding,
    load_ai_canonical_roster,
    model_sha256,
    response_schema_sha256,
)
from cobol_archaeologist.migration.contracts import MigrationEvidencePin

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_AMENDMENT_SOURCES = {
    "src/cobol_archaeologist/migration/ai_review.py",
    "scripts/seal_r2_review_session.py",
    "scripts/prepare_r2_reviews.py",
    "scripts/promote_r2_review_roster.py",
}


def encoded(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def pin(root, name):
    return MigrationEvidencePin(
        path=name, sha256=hashlib.sha256((root / name).read_bytes()).hexdigest()
    )


def read(root, evidence):
    return _pinned(root, MigrationEvidencePin.model_validate(evidence))


def json_pin(root, evidence):
    return json.loads(read(root, evidence))


def immutable(path, raw):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"immutable promotion artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def check_nested_pins(root, value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            read(root, {"path": value["path"], "sha256": value["sha256"]})
        else:
            for nested in value.values():
                check_nested_pins(root, nested)
    elif isinstance(value, list):
        for nested in value:
            check_nested_pins(root, nested)


def runtime_snapshot(root, manifest, inventory=None):
    archive = manifest.get("archive") or {
        "path": manifest["archive_path"],
        "sha256": manifest["archive_sha256"],
    }
    read(root, archive)
    if inventory is None:
        return
    files = manifest["files"]
    listed = (
        {p["path"]: p["sha256"] for p in files} if isinstance(files, list) else files
    )
    if listed != inventory or (isinstance(files, list) and len(files) != len(listed)):
        raise ValueError("runtime snapshot inventory differs")
    with zipfile.ZipFile(root / archive["path"]) as bundle:
        if len(bundle.namelist()) != len(inventory) or set(bundle.namelist()) != set(
            inventory
        ):
            raise ValueError("runtime archive member inventory differs")
        for name, digest in inventory.items():
            if hashlib.sha256(bundle.read(name)).hexdigest() != digest:
                raise ValueError("runtime archive source checksum differs")


def review_runtime(root, out, protocol):
    """Verify the original archive and any explicit, narrowly scoped correction."""
    original_inventory_pin = pin(out, "runtime-source-inventory.json")
    original = json_pin(out, original_inventory_pin)
    if original_inventory_pin.sha256 != protocol.runtime_source_sha256 or not original:
        raise ValueError("review runtime inventory protocol identity differs")
    original_snapshot_pin = pin(out, "runtime-source-manifest.json")
    original_snapshot = json_pin(out, original_snapshot_pin)
    if (
        original_snapshot.get("schema_version")
        != "migration-ai-review-runtime-snapshot-v1"
        or MigrationEvidencePin.model_validate(original_snapshot["inventory"])
        != original_inventory_pin
    ):
        raise ValueError("review runtime snapshot binding differs")
    runtime_snapshot(out, original_snapshot, original)
    inventory, snapshot_pin, amendment_pin = original, original_snapshot_pin, None
    amendment_path = out / "review-capture-amendment.json"
    if amendment_path.exists():
        amendment_pin = pin(out, amendment_path.name)
        amendment = json_pin(out, amendment_pin)
        if (
            amendment.get("schema_version")
            != "migration-ai-review-capture-amendment-v1"
            or amendment.get("reason") != "exact_prior_final_citation_gate_correction"
            or amendment.get("request_input_schema_hashes_unchanged") is not True
            or amendment.get("semantic_decisions_unchanged") is not True
        ):
            raise ValueError("unsupported review capture amendment")
        if (
            MigrationEvidencePin.model_validate(amendment["protocol"])
            != pin(out, "review-protocol.json")
            or MigrationEvidencePin.model_validate(
                amendment["original_runtime_inventory"]
            )
            != original_inventory_pin
            or MigrationEvidencePin.model_validate(
                amendment["original_runtime_snapshot_manifest"]
            )
            != original_snapshot_pin
        ):
            raise ValueError(
                "capture amendment original protocol/runtime binding differs"
            )
        unchanged = amendment["unchanged_bindings"]
        if (
            MigrationEvidencePin.model_validate(unchanged["protocol"])
            != pin(out, "review-protocol.json")
            or unchanged["response_schema_sha256"] != protocol.response_schema_sha256
            or tuple(
                MigrationEvidencePin.model_validate(p) for p in unchanged["case_inputs"]
            )
            != protocol.case_inputs
        ):
            raise ValueError("capture amendment changed protocol/input/schema identity")
        for item in protocol.case_inputs:
            read(out, item)
        actual_requests = {
            p.relative_to(out).as_posix()
            for p in (out / "requests").rglob("request.json")
        }
        request_entries = unchanged["requests"]
        pinned_requests = {entry["request"]["path"] for entry in request_entries}
        blind_requests = {
            f"requests/{AICaseSpec.model_validate_json(read(out, case_pin)).case_id}/{role}/request.json"
            for case_pin in protocol.case_inputs
            for role in ROLES[:2]
        }
        if (
            len(request_entries) != len(pinned_requests)
            or not blind_requests <= pinned_requests
            or not pinned_requests <= actual_requests
        ):
            raise ValueError(
                "capture amendment must pin every unchanged blind review request"
            )
        for entry in request_entries:
            request = AIReviewRequest.model_validate_json(read(out, entry["request"]))
            if (
                model_sha256(request) != entry["request_sha256"]
                or request.protocol != pin(out, "review-protocol.json")
                or request.case_input not in protocol.case_inputs
                or request.response_schema_sha256 != protocol.response_schema_sha256
            ):
                raise ValueError("capture amendment request identity changed")
        amended_pin = MigrationEvidencePin.model_validate(
            amendment["amended_runtime_inventory"]
        )
        inventory = json_pin(out, amended_pin)
        snapshot_pin = MigrationEvidencePin.model_validate(
            amendment["amended_runtime_snapshot_manifest"]
        )
        snapshot = json_pin(out, snapshot_pin)
        if (
            snapshot.get("schema_version") != "migration-ai-review-runtime-snapshot-v1"
            or MigrationEvidencePin.model_validate(snapshot["inventory"]) != amended_pin
        ):
            raise ValueError("amended runtime snapshot binding differs")
        if set(inventory) != set(original):
            raise ValueError("capture amendment may not add or remove runtime paths")
        changed = {name for name in original if original[name] != inventory[name]}
        if not changed or changed - CAPTURE_AMENDMENT_SOURCES:
            raise ValueError("capture amendment changes an unauthorized runtime source")
        expected_changes = [
            {"path": name, "old_sha256": original[name], "new_sha256": inventory[name]}
            for name in sorted(changed)
        ]
        if amendment["changed_sources"] != expected_changes:
            raise ValueError("capture amendment changed-source accounting differs")
        runtime_snapshot(out, snapshot, inventory)
    for name, digest in inventory.items():
        read(root, {"path": name, "sha256": digest})
    actual_source_paths = {
        p.relative_to(root).as_posix() for p in (root / "src").rglob("*.py")
    }
    if actual_source_paths != {name for name in inventory if name.startswith("src/")}:
        raise ValueError("review runtime source inventory changed")
    return original_snapshot_pin, snapshot_pin, amendment_pin


def prerequisites(root, out, protocol, case_ids):
    terminal_pin = pin(root, "data/eval/m4/terminal-receipt.json")
    terminal = json_pin(root, terminal_pin)
    if (
        terminal.get("status") != "COMPLETE"
        or terminal.get("pending_evaluation_keys") != 0
    ):
        raise ValueError("R1.7 intake is not terminal")
    for name, digest in terminal["artifacts"].items():
        read(root, {"path": f"data/eval/m4/{name}", "sha256": digest})
    manifest_pin = pin(root, "data/eval/m4/evaluation-manifest.json")
    manifest = json_pin(root, manifest_pin)
    check_nested_pins(root, manifest)
    decision_pin = MigrationEvidencePin.model_validate(manifest["decision"])
    intake_pin = MigrationEvidencePin.model_validate(manifest["r2_input_roster"])
    decision, intake = json_pin(root, decision_pin), json_pin(root, intake_pin)
    check_nested_pins(root, intake)
    if decision.get("configuration") != 4 or intake.get("configuration") != 4:
        raise ValueError(
            "R2 requires configuration-4 intake, not a human configuration-3 alias"
        )
    if (
        decision.get("status") != "NOT_EVALUABLE"
        or MigrationEvidencePin.model_validate(intake["decision"]) != decision_pin
    ):
        raise ValueError("unsupported detector decision or intake binding")
    detector = intake["detector_led"]
    oracle = intake["oracle_assisted"]
    if detector != {"active": False, "count": 0, "eligible_findings": []}:
        raise ValueError("non-evaluable detector cannot authorize detector-led cases")
    if oracle["candidate_count"] != 12 or tuple(oracle["candidate_ids"]) != tuple(
        case_ids
    ):
        raise ValueError("review protocol differs from exact R1 oracle intake order")
    if read(root, intake["candidate_manifest"]) != read(
        out, protocol.candidate_manifest
    ):
        raise ValueError("review candidate manifest differs from intake")
    temporal_pin = MigrationEvidencePin.model_validate(
        intake["temporal_review_manifest"]
    )
    temporal = json_pin(root, temporal_pin)
    check_nested_pins(root, temporal)
    if (
        temporal.get("finalized") is not True
        or temporal.get("evaluation_ready") is not True
        or temporal["target_pair_count"] != 20
        or temporal["evaluation_side_count"] != 40
        or len(temporal["pair_order"]) != 20
        or len(set(temporal["pair_order"])) != 20
        or len(temporal["instance_order"]) != 40
        or len(set(temporal["instance_order"])) != 40
    ):
        raise ValueError(
            "T6 temporal prerequisite is not exact promoted 20-pair/40-side evidence"
        )
    temporal_rows = [
        json.loads(line)
        for line in read(root, temporal["evaluation_rows"]).decode().splitlines()
        if line.strip()
    ]
    if tuple(row["instance_id"] for row in temporal_rows) != tuple(
        temporal["instance_order"]
    ):
        raise ValueError("temporal evaluation row order differs")
    historical_pin = pin(root, "data/eval/m4/runtime-source-manifest.json")
    if (
        terminal["artifacts"].get("runtime-source-manifest.json")
        != historical_pin.sha256
        or terminal.get("runtime_snapshot_reproduces_frozen_hash") is not True
    ):
        raise ValueError("R1 runtime snapshot prerequisite differs")
    runtime_snapshot(root, json_pin(root, historical_pin))
    # DECISION: Only the explicit citation-gate correction can amend the capture
    # runtime; it never replaces the original protocol or archived source bytes.
    original_snapshot_pin, snapshot_pin, amendment_pin = review_runtime(
        root, out, protocol
    )
    result = {
        "evaluation_manifest": manifest_pin.model_dump(),
        "detector_decision": decision_pin.model_dump(),
        "input_roster": intake_pin.model_dump(),
        "r1_terminal_receipt": terminal_pin.model_dump(),
        "temporal_review_manifest": temporal_pin.model_dump(),
        "r1_runtime_snapshot_manifest": historical_pin.model_dump(),
        "review_runtime_snapshot_manifest": {
            "path": "data/migration/ai-review/" + snapshot_pin.path,
            "sha256": snapshot_pin.sha256,
        },
    }
    if amendment_pin is not None:
        result["original_review_runtime_snapshot_manifest"] = {
            "path": "data/migration/ai-review/" + original_snapshot_pin.path,
            "sha256": original_snapshot_pin.sha256,
        }
        result["review_capture_amendment"] = {
            "path": "data/migration/ai-review/" + amendment_pin.path,
            "sha256": amendment_pin.sha256,
        }
        result["runtime_provenance"] = (
            "original_protocol_runtime_preserved_with_explicit_prior_citation_capture_amendment"
        )
    return result


def waves(ids, cap, prefix):
    return [
        {
            "section": f"R2.{prefix + start // cap}",
            "track": "oracle_assisted",
            "ordinal_start": start + 1,
            "ordinal_end": min(start + cap, len(ids)),
            "case_ids": list(ids[start : start + cap]),
        }
        for start in range(0, len(ids), cap)
    ]


def promote(root: Path = ROOT):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    migration = root / "data/migration"
    protocol_pin = pin(out, "review-protocol.json")
    protocol = AIReviewProtocol.model_validate_json(read(out, protocol_pin))
    if (
        len(protocol.case_inputs) != 12
        or protocol.response_schema_sha256 != response_schema_sha256()
    ):
        raise ValueError("promotion requires exact frozen twelve-case review protocol")
    read(out, protocol.authorization_evidence)
    read(out, protocol.candidate_manifest)
    specs = tuple(
        AICaseSpec.model_validate_json(read(out, p)) for p in protocol.case_inputs
    )
    case_ids = tuple(spec.case_id for spec in specs)
    if len(set(case_ids)) != 12:
        raise ValueError("duplicate protocol cases")
    intake = prerequisites(root, out, protocol, case_ids)
    retained, accepted, excluded = [], [], []
    used_tasks, used_sessions = set(), set()
    # Verify all 36 graphs before writing any case evidence or eligible roster.
    for spec, case_pin in zip(specs, protocol.case_inputs, strict=True):
        required = (
            *spec.source_evidence,
            spec.regulation_evidence,
            *spec.fixture_evidence,
        )
        for evidence in required:
            read(out, evidence)
        captures, responses, events_by_role, final_pins, response_records = (
            [],
            [],
            {},
            [],
            [],
        )
        for role in ROLES:
            try:
                capture_pin = pin(out, f"reviews/{spec.case_id}/{role}/capture.json")
            except OSError as error:
                raise ValueError(
                    "missing role: all 36 sealed captures required"
                ) from error
            cap = AIReviewCapture.model_validate_json(read(out, capture_pin))
            req = AIReviewRequest.model_validate_json(read(out, cap.request))
            events = AIHostSessionEvents.model_validate_json(read(out, cap.host_events))
            response = AIReviewResponse.model_validate_json(read(out, cap.exact_final))
            if (
                req.case_id != spec.case_id
                or req.case_input != case_pin
                or req.protocol != protocol_pin
                or req.reviewer.role != role
                or req.reviewer not in protocol.reviewers
                or events.reviewer != req.reviewer
                or req.response_schema_sha256 != protocol.response_schema_sha256
                or cap.request_sha256 != model_sha256(req)
                or events.request_sha256 != cap.request_sha256
                or events.final_sha256 != cap.exact_final.sha256
                or response.case_id != spec.case_id
                or response.role != role
            ):
                raise ValueError("sealed capture case/protocol/model identity differs")
            if not protocol.frozen_at < events.started_at < events.completed_at:
                raise ValueError("sealed capture timing differs")
            if events.task_id in used_tasks or events.session_id in used_sessions:
                raise ValueError("reused review task or session")
            used_tasks.add(events.task_id)
            used_sessions.add(events.session_id)
            read(out, events.raw_transcript)
            read(out, req.prompt)
            expected_sets = [set(required)]
            if role == "ai_adjudicator":
                expected_sets.append({*required, *req.prior_responses})
            if (
                len(response.evidence) != len(set(response.evidence))
                or set(response.evidence) not in expected_sets
            ):
                raise ValueError(
                    "response evidence does not equal frozen case evidence"
                )
            if role == "ai_adjudicator" and (
                req.prior_responses != tuple(final_pins)
                or events.started_at
                <= max(event.completed_at for event in events_by_role.values())
            ):
                raise ValueError(
                    "adjudicator does not follow/bind both independent sealed finals"
                )
            final_pins.append(cap.exact_final)
            events_by_role[role] = events
            captures.append(capture_pin)
            responses.append(response)
            response_records.append(
                {
                    "role": role,
                    "exact_final": cap.exact_final.model_dump(),
                    "decision": response.decision,
                    "rationale": response.rationale,
                    "unresolved_issues": list(response.unresolved_issues),
                }
            )
        included = all(
            r.decision == "include" and not r.unresolved_issues for r in responses
        )
        (accepted if included else excluded).append(spec.case_id)
        evidence = AIReviewEvidence(
            case_id=spec.case_id,
            case_input=case_pin,
            protocol=protocol_pin,
            captures=captures,
        )
        evidence_name = f"evidence/{spec.case_id}.json"
        evidence_raw = encoded(evidence)
        evidence_pin = MigrationEvidencePin(
            path=evidence_name, sha256=hashlib.sha256(evidence_raw).hexdigest()
        )
        retained.append((spec, evidence_pin, evidence_raw, response_records))
    status = (
        "NOT_EVALUABLE"
        if not accepted
        else "COMPLETE_WITH_EXCLUSIONS"
        if excluded
        else "COMPLETE_ALL_ACCEPTED"
    )
    disposition = AIReviewDispositionManifest(
        protocol=protocol_pin,
        cases=[
            {"case_id": spec.case_id, "review_evidence": evidence_pin}
            for spec, evidence_pin, _, _ in retained
        ],
        accepted_case_ids=accepted,
        excluded_case_ids=excluded,
        status=status,
    )
    pending = {out / evidence_pin.path: raw for _, evidence_pin, raw, _ in retained}
    pending[out / "disposition.json"] = encoded(disposition)
    pending[out / "disposition-reasons.json"] = encoded(
        {
            "status": status,
            "acceptance_policy": disposition.acceptance_policy,
            "cases": [
                {
                    "case_id": spec.case_id,
                    "accepted": spec.case_id in accepted,
                    "responses": records,
                }
                for spec, _, _, records in retained
            ],
        }
    )
    canonical = []
    bindings = []
    for spec, evidence_pin, _, _ in retained:
        payload = spec.model_dump(mode="json")
        bindings.append(
            _ReviewCaseBinding(
                **payload,
                review_protocol_sha256=protocol_pin.sha256,
                review_evidence_sha256=evidence_pin.sha256,
                review_evidence=evidence_pin,
            )
        )
        if spec.case_id in accepted:
            payload.pop("schema_version")
            canonical.append(
                AICanonicalMigrationCase(
                    **payload,
                    review_protocol_sha256=protocol_pin.sha256,
                    review_evidence_sha256=evidence_pin.sha256,
                    review_evidence=evidence_pin,
                )
            )
    canonical_raw = (
        "\n".join(case.model_dump_json() for case in canonical)
        + ("\n" if canonical else "")
    ).encode()
    pending[migration / "cases.jsonl"] = canonical_raw
    pending[migration / "oracle-assisted-roster.jsonl"] = canonical_raw
    pending[migration / "detector-led-roster.jsonl"] = b""
    wave_map = {
        "schema_version": "r2-migration-wave-map-v1",
        "generation_cap": 6,
        "validation_cap": 8,
        "generation_waves": waves(accepted, 6, 3),
        "validation_waves": waves(accepted, 8, 7),
        "skipped_generation_sections": ["R2.5", "R2.6"],
        "provider_calls": 0,
    }
    pending[migration / "wave-map.json"] = encoded(wave_map)

    def planned_pin(path):
        return {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(pending[path]).hexdigest(),
        }

    manifest = {
        "schema_version": "r2-reviewed-roster-manifest-v1",
        "status": status,
        "configuration": 4,
        "review_provenance": protocol.review_provenance,
        "nonhuman": True,
        "review_protocol": {
            "path": "data/migration/ai-review/" + protocol_pin.path,
            "sha256": protocol_pin.sha256,
        },
        "candidate_manifest": {
            "path": "data/migration/ai-review/" + protocol.candidate_manifest.path,
            "sha256": protocol.candidate_manifest.sha256,
        },
        "candidate_inputs": [p.model_dump() for p in protocol.case_inputs],
        "review_evidence_root": "data/migration/ai-review",
        "case_evidence": [
            {"case_id": spec.case_id, "pin": evidence_pin.model_dump()}
            for spec, evidence_pin, _, _ in retained
        ],
        "disposition": planned_pin(out / "disposition.json"),
        "disposition_reasons": planned_pin(out / "disposition-reasons.json"),
        "canonical_roster": planned_pin(migration / "cases.jsonl"),
        "oracle_assisted_roster": planned_pin(
            migration / "oracle-assisted-roster.jsonl"
        ),
        "detector_led_roster": planned_pin(migration / "detector-led-roster.jsonl"),
        "wave_map": planned_pin(migration / "wave-map.json"),
        "source_intake": intake,
        "accepted_case_ids": accepted,
        "excluded_case_ids": excluded,
        "generation_denominators": {
            "detector_led": 0,
            "oracle_assisted": len(accepted),
            "combined": len(accepted),
        },
        "distinct_accepted_source_bundles": len(
            {case.source_bundle_group for case in canonical}
        ),
        "provider_calls": 0,
        "generation_authorized": False,
        "generation_remaining_gate": "R2.2 frozen Luna/max requests, real validation backend and separate sealed qualification",
    }
    if "review_capture_amendment" in intake:
        manifest["review_capture_amendment"] = intake["review_capture_amendment"]
        manifest["capture_runtime_provenance"] = intake["runtime_provenance"]
    pending[migration / "roster-manifest.json"] = encoded(manifest)
    for path, raw in pending.items():
        if path.exists() and path.read_bytes() != raw:
            raise ValueError(f"immutable promotion artifact differs: {path}")
    # Evidence is retained before validating the existing loader's complete chain.
    for _, evidence_pin, raw, _ in retained:
        immutable(out / evidence_pin.path, raw)
    _load_review_chain(
        migration / "cases.jsonl",
        review_evidence_root=out,
        protocol_path=out / protocol_pin.path,
        reviewed_bindings=tuple(bindings),
        require_inclusion=False,
    )
    with tempfile.TemporaryDirectory(prefix="r2-promotion-") as staging:
        staged = Path(staging)
        (staged / "cases.jsonl").write_bytes(canonical_raw)
        (staged / "disposition.json").write_bytes(encoded(disposition))
        validated = load_ai_canonical_roster(
            staged / "cases.jsonl",
            review_evidence_root=out,
            protocol_path=out / protocol_pin.path,
            disposition_path=staged / "disposition.json",
        )
        if tuple(validated) != tuple(canonical):
            raise ValueError("promotion replay differs from canonical accepted subset")
    for path, raw in pending.items():
        immutable(path, raw)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(promote(args.root), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
