"""Reconcile preserved original reviews and freshly reviewed bounded revisions.

No provider calls are made. Original terminal reviews are retained as exclusions;
only the independently reviewed revision subset may enter the canonical roster.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICanonicalMigrationCase,
    AICaseSpec,
    AIReviewDispositionManifest,
    AIReviewEvidence,
    AIReviewProtocol,
    AIReviewResponse,
    _load_review_chain,
    _ReviewCaseBinding,
    load_ai_canonical_roster,
)

ROOT = Path(__file__).resolve().parents[1]
REVISION_IDS = tuple(
    f"migration_{value}" for value in ("075075", "255807", "191889", "345332")
)
NEW_SCRIPTS = (
    "scripts/prepare_r2_review_revisions.py",
    "scripts/prepare_r2_revision_reviews.py",
    "scripts/promote_r2_review_revisions.py",
    "scripts/wsl_migration_backend.py",
)


def helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD = helper("promote_r2_review_roster")
BUILDER = helper("prepare_r2_reviews")
encoded, pin, read, json_pin, immutable = (
    OLD.encoded,
    OLD.pin,
    OLD.read,
    OLD.json_pin,
    OLD.immutable,
)


def check_revision(original, revised):
    """Fixture/behavior repairs cannot replace identity, sources, or expand scope."""
    protected = (
        "case_id",
        "instance_id",
        "drift_type",
        "stratum",
        "validation_capability",
        "primary_program",
        "frozen_sources",
        "source_evidence",
        "regulation_evidence",
        "affected_hosts",
        "detector_input_ref",
        "validation_protocol_sha256",
        "source_bundle_group",
    )
    for field in protected:
        if getattr(original, field) != getattr(revised, field):
            raise ValueError(
                f"revision changed original identity/source binding: {field}"
            )
    if revised.oracle_evidence_ref not in (
        original.oracle_evidence_ref,
        f"revisions/inputs/{revised.case_id}/proposal.json",
    ):
        raise ValueError("revision oracle reference must name its bounded proposal")
    scopes = {scope.path: scope.line_spans for scope in original.allowed_source_scope}
    for scope in revised.allowed_source_scope:
        spans = scopes.get(scope.path, ())
        for start, end in scope.line_spans:
            # Cover an interval with the union of original spans, allowing overlaps.
            cursor = start
            for low, high in sorted(spans):
                if low <= cursor <= high:
                    cursor = max(cursor, high + 1)
            if cursor <= end:
                raise ValueError("revision scope expands original allowed lines")


def collect(out, protocol_path, prefix, ids, contexts):
    protocol_pin = pin(out, protocol_path)
    protocol = AIReviewProtocol.model_validate_json(read(out, protocol_pin))
    specs = tuple(
        AICaseSpec.model_validate_json(read(out, p)) for p in protocol.case_inputs
    )
    if tuple(case.case_id for case in specs) != tuple(ids):
        raise ValueError("review protocol differs from exact ordered case subset")
    if protocol.response_schema_sha256 != BUILDER.response_schema_sha256():
        raise ValueError("review response schema changed")
    read(out, protocol.authorization_evidence)
    read(out, protocol.candidate_manifest)
    records, accepted, excluded, planned, bindings = [], [], [], {}, []
    latest_completion = protocol.frozen_at
    for spec, case_pin in zip(specs, protocol.case_inputs, strict=True):
        captures, finals, events_by_role, responses = [], [], {}, []
        for role in ROLES:
            name = f"{prefix}reviews/{spec.case_id}/{role}/capture.json"
            try:
                capture_pin = pin(out, name)
            except OSError as error:
                raise ValueError(
                    "missing role: all 36 original and 12 revision captures required"
                ) from error
            cap, req, events, raw = BUILDER.validate_capture(
                out,
                capture_pin,
                protocol=protocol_pin,
                case_pin=case_pin,
                role=role,
            )
            if events.task_id in contexts[0] or events.session_id in contexts[1]:
                raise ValueError("reused original/revision review task or session")
            contexts[0].add(events.task_id)
            contexts[1].add(events.session_id)
            latest_completion = max(latest_completion, events.completed_at)
            if role == ROLES[2] and (
                req.prior_responses != tuple(finals)
                or events.started_at
                <= max(e.completed_at for e in events_by_role.values())
            ):
                raise ValueError(
                    "adjudicator must follow both fresh independent finals"
                )
            response = AIReviewResponse.model_validate_json(raw)
            responses.append(response)
            finals.append(cap.exact_final)
            events_by_role[role] = events
            captures.append(capture_pin)
            records.append(
                {
                    "case_id": spec.case_id,
                    "role": role,
                    "capture": capture_pin.model_dump(),
                }
            )
        include = all(
            r.decision == "include" and not r.unresolved_issues for r in responses
        )
        (accepted if include else excluded).append(spec.case_id)
        evidence = AIReviewEvidence(
            case_id=spec.case_id,
            case_input=case_pin,
            protocol=protocol_pin,
            captures=captures,
        )
        name = (
            f"{prefix}evidence/{spec.case_id}.json"
            if prefix
            else f"original-review-evidence/{spec.case_id}.json"
        )
        raw = encoded(evidence)
        evidence_pin = OLD.MigrationEvidencePin(
            path=name, sha256=hashlib.sha256(raw).hexdigest()
        )
        planned[out / name] = raw
        bindings.append(
            _ReviewCaseBinding(
                **spec.model_dump(),
                review_protocol_sha256=protocol_pin.sha256,
                review_evidence_sha256=evidence_pin.sha256,
                review_evidence=evidence_pin,
            )
        )
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
            {"case_id": b.case_id, "review_evidence": b.review_evidence}
            for b in bindings
        ],
        accepted_case_ids=accepted,
        excluded_case_ids=excluded,
        status=status,
    )
    return (
        protocol_pin,
        protocol,
        specs,
        bindings,
        disposition,
        records,
        planned,
        latest_completion,
    )


def runtime(root, out, protocol):
    inventory_pin = pin(out, "revisions/runtime-source-inventory.json")
    inventory = json_pin(out, inventory_pin)
    if inventory_pin.sha256 != protocol.runtime_source_sha256:
        raise ValueError("revision runtime protocol inventory differs")
    expected = set(BUILDER.inventory(root)) | set(NEW_SCRIPTS)
    if set(inventory) != expected:
        raise ValueError(
            "revision runtime inventory must contain exact source and script paths"
        )
    for name, digest in inventory.items():
        read(root, {"path": name, "sha256": digest})
    snapshot_pin = pin(out, "revisions/runtime-source-manifest.json")
    snapshot = json_pin(out, snapshot_pin)
    if (
        snapshot.get("schema_version") != "migration-ai-review-runtime-snapshot-v1"
        or OLD.MigrationEvidencePin.model_validate(snapshot["inventory"])
        != inventory_pin
    ):
        raise ValueError("revision runtime snapshot binding differs")
    OLD.runtime_snapshot(out, snapshot, inventory)
    return snapshot_pin


def revised_baseline(out, specs, originals):
    """Retain real original-source results for every newly authored fixture."""
    qualification_pin = pin(
        out, "revisions/revised-original-baseline-qualification.json"
    )
    raw = read(out, qualification_pin)
    fixtures, observations = {}, {}
    for spec in specs:
        fixture_pins = [
            p for p in spec.fixture_evidence if p.path.endswith("/fixtures.json")
        ]
        observation_pins = [
            p
            for p in spec.fixture_evidence
            if p.path.endswith("/revised-original-observations.json")
        ]
        if len(fixture_pins) != 1 or len(observation_pins) != 1:
            raise ValueError(
                "revision requires exact concrete fixtures and revised original observations"
            )
        fixtures[spec.case_id] = json_pin(out, fixture_pins[0])
        observation = json_pin(out, observation_pins[0])
        if (
            observation.get("schema_version")
            != "migration-revised-original-baseline-observations-v1"
            or OLD.MigrationEvidencePin.model_validate(observation["qualification"])
            != qualification_pin
            or OLD.MigrationEvidencePin.model_validate(observation["fixtures"])
            != fixture_pins[0]
            or OLD.MigrationEvidencePin.model_validate(
                observation["original_case_input"]
            )
            != originals[spec.case_id]
        ):
            raise ValueError("revision baseline source/fixture binding differs")
        observations[spec.case_id] = observation["case"]
    author = helper("prepare_r2_review_revisions")
    rows = author.verified_revised_baseline(raw, fixtures)
    if rows != observations:
        raise ValueError(
            "revision observations differ from complete real execution qualification"
        )
    if json.loads(raw).get("execution_environment") == "linux-wsl" or any(
        p.path.endswith("/qualified-capability.json")
        for spec in specs
        for p in spec.fixture_evidence
    ):
        capability_pin = pin(out, "revisions/qualified-wsl-capabilities.json")
        receipt, capabilities = author.verified_wsl_capabilities(
            out.parents[2], read(out, capability_pin), raw, rows, fixtures
        )
        if receipt["backend_script"]["path"] != "scripts/wsl_migration_backend.py":
            raise ValueError("revision WSL backend is outside frozen runtime inventory")
        for spec in specs:
            pins = [
                p
                for p in spec.fixture_evidence
                if p.path.endswith("/qualified-capability.json")
            ]
            if len(pins) != 1:
                raise ValueError(
                    "revised WSL case requires measured capability evidence"
                )
            measured = json_pin(out, pins[0])
            if (
                measured.get("schema_version")
                != "migration-case-qualified-wsl-capability-v1"
                or measured.get("case_id") != spec.case_id
                or OLD.MigrationEvidencePin.model_validate(measured["qualification"])
                != capability_pin
                or measured.get("backend") != capabilities[spec.case_id]
                or measured.get("backend_script") != receipt["backend_script"]
                or measured.get("qualification_artifact")
                != receipt.get("qualification_artifact")
                or OLD.MigrationEvidencePin.model_validate(
                    measured["actual_original_execution"]
                )
                not in spec.fixture_evidence
            ):
                raise ValueError("measured WSL revision capability binding differs")
    return qualification_pin


def promote(root: Path = ROOT):
    root = Path(root).resolve()
    out, migration = root / "data/migration/ai-review", root / "data/migration"
    original_protocol = AIReviewProtocol.model_validate_json(
        (out / "review-protocol.json").read_bytes()
    )
    original_ids = tuple(
        AICaseSpec.model_validate_json(read(out, p)).case_id
        for p in original_protocol.case_inputs
    )
    if len(original_ids) != 12 or len(set(original_ids)) != 12:
        raise ValueError("exact original twelve candidate inputs required")
    intake = OLD.prerequisites(root, out, original_protocol, original_ids)
    contexts = (set(), set())
    original = collect(out, "review-protocol.json", "", original_ids, contexts)
    receipt_pin = pin(out, "original-review-receipt.json")
    receipt = json_pin(out, receipt_pin)
    if (
        receipt.get("schema_version") != "migration-ai-original-review-receipt-v1"
        or receipt.get("status") != "COMPLETE_36_REVIEWED_NOT_GENERATION_ELIGIBLE"
        or receipt.get("terminal_status") != "ALL_ORIGINAL_REVIEWS_TERMINAL"
        or receipt.get("capture_count") != 36
        or OLD.MigrationEvidencePin.model_validate(receipt["protocol"]) != original[0]
        or receipt.get("reviews") != original[5]
        or tuple(receipt.get("accepted_original_case_ids", ()))
        != original[4].accepted_case_ids
    ):
        raise ValueError(
            "original terminal receipt differs from all 36 retained chains"
        )
    # This revision route accounts for an original roster with no eligible cases.
    if original[4].accepted_case_ids:
        raise ValueError("original reviews unexpectedly authorize generation")
    if tuple(case for case in original_ids if case in REVISION_IDS) != REVISION_IDS:
        raise ValueError("revision ids must retain original intake order")
    revised = collect(
        out, "revisions/review-protocol.json", "revisions/", REVISION_IDS, contexts
    )
    if (
        revised[1].frozen_at <= original[7]
        or revised[1].candidate_manifest != original[1].candidate_manifest
    ):
        raise ValueError(
            "revision protocol must be fresh with unchanged original intake"
        )
    originals = {spec.case_id: spec for spec in original[2]}
    for spec in revised[2]:
        check_revision(originals[spec.case_id], spec)
    baseline_pin = revised_baseline(
        out, revised[2], dict(zip(original_ids, original[1].case_inputs, strict=True))
    )
    snapshot_pin = runtime(root, out, revised[1])
    pending = {**original[6], **revised[6]}
    original_disposition = out / "original-review-disposition.json"
    revision_disposition = out / "revisions/disposition.json"
    pending[original_disposition] = encoded(original[4])
    pending[revision_disposition] = encoded(revised[4])
    accepted = list(revised[4].accepted_case_ids)
    canonical = []
    for binding in revised[3]:
        if binding.case_id in accepted:
            payload = binding.model_dump()
            payload.pop("schema_version")
            canonical.append(AICanonicalMigrationCase(**payload))
    roster_raw = (
        "\n".join(case.model_dump_json() for case in canonical)
        + ("\n" if canonical else "")
    ).encode()
    for name in ("cases.jsonl", "oracle-assisted-roster.jsonl"):
        pending[migration / name] = roster_raw
    pending[migration / "detector-led-roster.jsonl"] = b""
    pending[migration / "wave-map.json"] = encoded(
        {
            "schema_version": "r2-migration-wave-map-v1",
            "generation_cap": 6,
            "validation_cap": 8,
            "generation_waves": OLD.waves(accepted, 6, 3),
            "validation_waves": OLD.waves(accepted, 8, 7),
            "skipped_generation_sections": ["R2.4", "R2.5", "R2.6"],
            "provider_calls": 0,
        }
    )

    def planned_pin(path):
        return {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(pending[path]).hexdigest(),
        }

    def rooted(evidence):
        return {
            "path": "data/migration/ai-review/" + evidence.path,
            "sha256": evidence.sha256,
        }

    manifest = {
        "schema_version": "r2-reviewed-revision-roster-manifest-v1",
        "status": revised[4].status,
        "configuration": 4,
        "detector_status": "NOT_EVALUABLE",
        "nonhuman": True,
        "review_provenance": revised[1].review_provenance,
        "source_intake": intake,
        "original_review_receipt": rooted(receipt_pin),
        "original_review_protocol": rooted(original[0]),
        "review_protocol": rooted(revised[0]),
        "review_evidence_root": "data/migration/ai-review",
        "revision_runtime_snapshot_manifest": rooted(snapshot_pin),
        "revised_original_baseline_qualification": rooted(baseline_pin),
        "original_disposition": planned_pin(original_disposition),
        "disposition": planned_pin(revision_disposition),
        "original_candidate_case_ids": list(original_ids),
        "original_candidate_count": 12,
        "original_review_capture_count": 36,
        "revision_review_capture_count": 12,
        "revision_case_ids": list(REVISION_IDS),
        "candidate_accounting": [
            {
                "case_id": case,
                "original_disposition": "excluded",
                "revision_disposition": "accepted"
                if case in accepted
                else "excluded"
                if case in REVISION_IDS
                else "not_revised",
                "generation_eligible": case in accepted,
            }
            for case in original_ids
        ],
        "accepted_case_ids": accepted,
        "original_excluded_case_ids": list(original[4].excluded_case_ids),
        "revision_excluded_case_ids": list(revised[4].excluded_case_ids),
        "excluded_case_ids": [case for case in original_ids if case not in accepted],
        "canonical_roster": planned_pin(migration / "cases.jsonl"),
        "oracle_assisted_roster": planned_pin(
            migration / "oracle-assisted-roster.jsonl"
        ),
        "detector_led_roster": planned_pin(migration / "detector-led-roster.jsonl"),
        "wave_map": planned_pin(migration / "wave-map.json"),
        "generation_denominators": {
            "detector_led": 0,
            "oracle_assisted": len(accepted),
            "combined": len(accepted),
        },
        "distinct_accepted_source_bundles": len(
            {case.source_bundle_group for case in canonical}
        ),
        "distinct_original_source_bundles": len(
            {case.source_bundle_group for case in original[2]}
        ),
        "distinct_revision_source_bundles": len(
            {case.source_bundle_group for case in revised[2]}
        ),
        "provider_calls": 0,
        "generation_authorized": False,
        "generation_remaining_gate": "R2.2 frozen Luna/max requests, real validation backend and separate sealed qualification",
    }
    pending[migration / "roster-manifest.json"] = encoded(manifest)
    for path, raw in pending.items():
        if path.exists() and path.read_bytes() != raw:
            raise ValueError(f"immutable promotion artifact differs: {path}")
    # Replay the existing typed loader against a complete staging tree before writes.
    import shutil

    with tempfile.TemporaryDirectory(prefix="r2-revision-promotion-") as directory:
        stage = Path(directory)
        shutil.copytree(out, stage / "ai-review")
        staged_out = stage / "ai-review"
        for path, raw in pending.items():
            if path.is_relative_to(out):
                staged_path = staged_out / path.relative_to(out)
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                staged_path.write_bytes(raw)
        for graph in (original, revised):
            _load_review_chain(
                stage / "cases.jsonl",
                review_evidence_root=staged_out,
                protocol_path=staged_out / graph[0].path,
                reviewed_bindings=tuple(graph[3]),
                require_inclusion=False,
            )
        (stage / "cases.jsonl").write_bytes(roster_raw)
        validated = load_ai_canonical_roster(
            stage / "cases.jsonl",
            review_evidence_root=staged_out,
            protocol_path=staged_out / revised[0].path,
            disposition_path=staged_out / "revisions/disposition.json",
        )
        if tuple(canonical) != validated:
            raise ValueError("revision canonical replay differs")
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
