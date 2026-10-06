"""Freeze four additive revised-input review chains; never rewrite original evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICaseSpec,
    AIReviewerIdentity,
    AIReviewProtocol,
    AIReviewRequest,
    AIReviewResponse,
    response_schema_sha256,
)
from cobol_archaeologist.migration.contracts import MigrationEvidencePin

ROOT = Path(__file__).resolve().parents[1]
_module = importlib.util.spec_from_file_location(
    "r2_original_request_builder", ROOT / "scripts/prepare_r2_reviews.py"
)
original = importlib.util.module_from_spec(_module)
_module.loader.exec_module(original)
CASE_IDS = tuple(
    "migration_" + suffix for suffix in ("075075", "255807", "191889", "345332")
)
REVISION_SCRIPTS = (
    "scripts/prepare_r2_review_revisions.py",
    "scripts/prepare_r2_revision_reviews.py",
    "scripts/promote_r2_review_revisions.py",
    "scripts/wsl_migration_backend.py",
)
QUALIFICATION = original.QUALIFICATION
save = original.save
read_pin = original.read_pin
pin_file = original.pin_file
validate_capture = original.validate_capture


def original_receipt(out):
    pin = pin_file(out, "original-review-receipt.json")
    receipt = json.loads(read_pin(out, pin))
    protocol_pin = pin_file(out, "review-protocol.json")
    protocol = AIReviewProtocol.model_validate_json(read_pin(out, protocol_pin))
    if (
        receipt.get("schema_version") != "migration-ai-original-review-receipt-v1"
        or receipt.get("terminal_status") != "ALL_ORIGINAL_REVIEWS_TERMINAL"
        or receipt.get("status") != "COMPLETE_36_REVIEWED_NOT_GENERATION_ELIGIBLE"
        or receipt.get("capture_count") != 36
        or MigrationEvidencePin.model_validate(receipt["protocol"]) != protocol_pin
    ):
        raise ValueError("all 36 terminal original reviews required")
    cases = {
        AICaseSpec.model_validate_json(read_pin(out, p)).case_id: p
        for p in protocol.case_inputs
    }
    rows = receipt["reviews"]
    if len(cases) != 12 or len(rows) != 36:
        raise ValueError("all 36 terminal original reviews required")
    captures, tasks, sessions = {}, set(), set()
    for item in rows:
        key = (item["case_id"], item["role"])
        if key in captures or key[0] not in cases or key[1] not in ROLES:
            raise ValueError("original review roster differs")
        row = validate_capture(
            out,
            item["capture"],
            protocol=protocol_pin,
            case_pin=cases[key[0]],
            role=key[1],
        )
        if row[2].task_id in tasks or row[2].session_id in sessions:
            raise ValueError("original review sessions reused")
        tasks.add(row[2].task_id)
        sessions.add(row[2].session_id)
        captures[key] = row
    for case_id in cases:
        primary, verifier, adjud = (captures[(case_id, role)] for role in ROLES)
        if adjud[1].prior_responses != (
            primary[0].exact_final,
            verifier[0].exact_final,
        ) or adjud[2].started_at <= max(
            primary[2].completed_at, verifier[2].completed_at
        ):
            raise ValueError("original adjudication prerequisites differ")
    return pin, protocol, cases, max(row[2].completed_at for row in captures.values())


def verified_inputs(out, originals):
    prep_pin = pin_file(out, "revisions/input-preparation.json")
    prep = json.loads(read_pin(out, prep_pin))
    pins = tuple(MigrationEvidencePin.model_validate(p) for p in prep["case_inputs"])
    if (
        len(pins) != 4
        or prep.get("candidate_count") != 4
        or prep.get("hidden_metadata_supplied") is not False
        or prep.get("generation_authorized") is not False
    ):
        raise ValueError("exact four blind unpromoted revision inputs required")
    cases = []
    protected = (
        "case_id",
        "instance_id",
        "stratum",
        "validation_capability",
        "primary_program",
        "frozen_sources",
        "source_evidence",
        "regulation_evidence",
        "source_bundle_group",
        "validation_protocol_sha256",
        "detector_input_ref",
    )
    for expected, pin in zip(CASE_IDS, pins, strict=True):
        if pin.path != f"revisions/inputs/{expected}/case-input.json":
            raise ValueError("revision inputs differ from exact ordered subset")
        raw = read_pin(out, pin)
        original.visible(json.loads(raw))
        spec = AICaseSpec.model_validate_json(raw)
        old = AICaseSpec.model_validate_json(read_pin(out, originals[expected]))
        if spec.case_id != expected or any(
            getattr(spec, field) != getattr(old, field) for field in protected
        ):
            raise ValueError(
                "revised source/regulation/identity pins differ from original"
            )
        if raw == read_pin(out, originals[expected]):
            raise ValueError("revised input must have a distinct proposal")
        if spec.oracle_evidence_ref not in (
            old.oracle_evidence_ref,
            f"revisions/inputs/{expected}/proposal.json",
        ):
            raise ValueError("revision oracle reference must name its bounded proposal")
        for evidence in (
            *spec.source_evidence,
            spec.regulation_evidence,
            *spec.fixture_evidence,
        ):
            content = read_pin(out, evidence)
            if evidence.path.endswith(".json"):
                original.visible(json.loads(content))
        if any(
            not p.path.startswith(f"revisions/inputs/{expected}/")
            for p in spec.fixture_evidence
        ):
            raise ValueError("revision fixtures must have distinct evidence paths")
        cases.append(spec)
    return prep_pin, pins, tuple(cases)


def runtime_inventory(root, out):
    old = json.loads((out / "runtime-source-inventory.json").read_bytes())
    # The old builder validates the amendment and both frozen ZIPs without rewriting.
    current_old = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in old
    }
    original.resume_runtime_pin(root, out, current_old)
    paths = set(old) | set(REVISION_SCRIPTS)
    paths.update(p.relative_to(root).as_posix() for p in (root / "src").rglob("*.py"))
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in sorted(paths)
    }


def materialize(
    out, spec, case_pin, protocol_pin, reviewer, prior=(), completed_after=None
):
    base = f"revisions/requests/{spec.case_id}/{reviewer.role}"
    prompt_pin = save(
        out, f"{base}/prompt.json", original.packet(out, spec, reviewer.role, prior)
    )
    request = AIReviewRequest(
        case_id=spec.case_id,
        reviewer=reviewer,
        protocol=protocol_pin,
        case_input=case_pin,
        prompt=prompt_pin,
        response_schema_sha256=response_schema_sha256(),
        prior_responses=prior,
    )
    request_pin = save(out, f"{base}/request.json", request)
    launch = (
        f"Read only the frozen single-case {reviewer.role} packet at {(out / prompt_pin.path).resolve().as_posix()}. "
        "Use a read-only command to read that file only. Do not inspect other files, repository history, "
        "cases or reviews; do not write files, generate patches, call providers or spawn agents. "
        "Follow its instructions and return only the exact JSON review as your final answer. "
        "This is explicitly nonhuman AI review. Launch in a fresh collaboration subagent with fork_turns none "
        "and the frozen gpt-6.1-sol medium identity."
    )
    launch_pin = save(out, f"{base}/launch.txt", launch.encode())
    save(
        out,
        f"{base}/launch-contract.json",
        {
            "request": request_pin.model_dump(),
            "prompt": prompt_pin.model_dump(),
            "launch": launch_pin.model_dump(),
            "reviewer": reviewer.model_dump(mode="json"),
            "fork_turns": "none",
            "read_only": True,
            "not_before": completed_after,
            "provider_calls": 0,
        },
    )
    return request


def prepare(root=ROOT, *, qualification_path=QUALIFICATION, frozen_at=None):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    qualification_pin = original.qualified(out, qualification_path)
    receipt_pin, old_protocol, originals, original_completed = original_receipt(out)
    prep_pin, pins, cases = verified_inputs(out, originals)
    runtime = runtime_inventory(root, out)
    existing = out / "revisions/review-protocol.json"
    frozen_time = (
        AIReviewProtocol.model_validate_json(existing.read_bytes()).frozen_at
        if existing.exists() and frozen_at is None
        else original.timestamp(frozen_at)
    )
    if frozen_time <= max(old_protocol.frozen_at, original_completed):
        raise ValueError("revision freeze must follow all original terminal reviews")
    runtime_pin = save(out, "revisions/runtime-source-inventory.json", runtime)
    authorization = pin_file(out, "authorization.json")
    read_pin(out, authorization)
    protocol = AIReviewProtocol(
        frozen_at=frozen_time,
        authorization_evidence=authorization,
        candidate_manifest=old_protocol.candidate_manifest,
        runtime_source_sha256=runtime_pin.sha256,
        response_schema_sha256=response_schema_sha256(),
        case_inputs=pins,
        reviewers=[
            AIReviewerIdentity(role=r, model="gpt-6.1-sol", reasoning="medium")
            for r in ROLES
        ],
    )
    read_pin(out, protocol.candidate_manifest)
    proto_pin = save(out, "revisions/review-protocol.json", protocol)
    save(out, "revisions/response-schema.json", AIReviewResponse.model_json_schema())
    save(
        out,
        "revisions/review-preparation.json",
        {
            "status": "FROZEN_REVISED_REVIEW_REQUESTS_ONLY",
            "protocol": proto_pin.model_dump(),
            "qualification": qualification_pin.model_dump(),
            "original_review_receipt": receipt_pin.model_dump(),
            "input_preparation": prep_pin.model_dump(),
            "runtime_inventory": runtime_pin.model_dump(),
            "case_count": 4,
            "blind_request_count": 8,
            "adjudicator_requests_require_two_sealed_captures": True,
            "provider_calls": 0,
            "generation_authorized": False,
        },
    )
    for case_pin, spec in zip(pins, cases, strict=True):
        for reviewer in protocol.reviewers[:2]:
            materialize(out, spec, case_pin, proto_pin, reviewer)
    return protocol


def adjudicator(
    case_id,
    *,
    root=ROOT,
    captures=None,
    materialized_at=None,
    qualification_path=QUALIFICATION,
):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    protocol = prepare(root, qualification_path=qualification_path)
    proto_pin = pin_file(out, "revisions/review-protocol.json")
    cases = {
        AICaseSpec.model_validate_json(read_pin(out, p)).case_id: p
        for p in protocol.case_inputs
    }
    if case_id not in cases:
        raise ValueError("unknown frozen revision case")
    if captures is None:
        try:
            captures = [
                pin_file(out, f"revisions/reviews/{case_id}/{role}/capture.json")
                for role in ROLES[:2]
            ]
        except OSError as error:
            raise ValueError(
                "both sealed independent revision captures required"
            ) from error
    if len(captures) != 2:
        raise ValueError("both sealed independent revision captures required")
    rows = [
        validate_capture(
            out, pin, protocol=proto_pin, case_pin=cases[case_id], role=role
        )
        for pin, role in zip(captures, ROLES[:2], strict=True)
    ]
    if (
        rows[0][2].task_id == rows[1][2].task_id
        or rows[0][2].session_id == rows[1][2].session_id
    ):
        raise ValueError("independent captures reused session/task")
    completed = max(row[2].completed_at for row in rows)
    if original.timestamp(materialized_at) <= completed:
        raise ValueError(
            "adjudicator cannot materialize before both revision captures completed"
        )
    spec = AICaseSpec.model_validate_json(read_pin(out, cases[case_id]))
    return materialize(
        out,
        spec,
        cases[case_id],
        proto_pin,
        protocol.reviewers[2],
        tuple(row[0].exact_final for row in rows),
        completed.isoformat(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--qualification", default=QUALIFICATION)
    parser.add_argument("--adjudicator")
    parser.add_argument("--primary-capture")
    parser.add_argument("--verifier-capture")
    args = parser.parse_args()
    if args.adjudicator:
        captures = None
        if args.primary_capture or args.verifier_capture:
            if not (args.primary_capture and args.verifier_capture):
                parser.error("both capture paths are required")
            out = args.root / "data/migration/ai-review"
            captures = [
                pin_file(out, name)
                for name in (args.primary_capture, args.verifier_capture)
            ]
        result = adjudicator(
            args.adjudicator,
            root=args.root,
            captures=captures,
            qualification_path=args.qualification,
        )
        print(result.model_dump_json())
    else:
        result = prepare(args.root, qualification_path=args.qualification)
        print(
            json.dumps(
                {
                    "case_count": len(result.case_inputs),
                    "provider_calls": 0,
                    "generation_authorized": False,
                }
            )
        )


if __name__ == "__main__":
    main()
