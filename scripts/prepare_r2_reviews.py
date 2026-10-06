"""Freeze blind, source-grounded nonhuman review requests without provider calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICaseSpec,
    AIHostSessionEvents,
    AIReviewCapture,
    AIReviewerIdentity,
    AIReviewProtocol,
    AIReviewRequest,
    AIReviewResponse,
    _pinned,
    model_sha256,
    response_schema_sha256,
)
from cobol_archaeologist.migration.contracts import MigrationEvidencePin

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = "qualification/transport-v1/qualification-receipt.json"
RUNTIME_SCRIPTS = (
    "scripts/prepare_r2_1.py",
    "scripts/prepare_r2_review_qualification.py",
    "scripts/prepare_r2_reviews.py",
    "scripts/seal_r2_review_session.py",
    "scripts/seal_r2_generation_session.py",
    "scripts/promote_r2_review_roster.py",
)
BANNED = {
    "provenance",
    "labels",
    "gold_rationale",
    "mutation",
    "annotator_notes",
    "detector_scores",
    "benchmark_scores",
}


def encoded(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def immutable_bytes(path: Path, payload: bytes):
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable review artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def save(out, name, value):
    payload = value if isinstance(value, bytes) else encoded(value)
    immutable_bytes(out / name, payload)
    return MigrationEvidencePin(path=name, sha256=hashlib.sha256(payload).hexdigest())


def read_pin(out, pin):
    return _pinned(out, MigrationEvidencePin.model_validate(pin))


def pin_file(out, name):
    return MigrationEvidencePin(
        path=name, sha256=hashlib.sha256((out / name).read_bytes()).hexdigest()
    )


def visible(value):
    if isinstance(value, dict):
        if BANNED & value.keys():
            raise ValueError("hidden metadata in review packet")
        for nested in value.values():
            visible(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            visible(nested)


def timestamp(value=None):
    result = datetime.now(UTC) if value is None else datetime.fromisoformat(str(value))
    if result.tzinfo is None:
        raise ValueError("review time requires timezone")
    return result


def inventory(root):
    # DECISION: Explicit source-file inventory excludes all future generated captures.
    paths = sorted(p.relative_to(root).as_posix() for p in (root / "src").rglob("*.py"))
    paths.extend(RUNTIME_SCRIPTS)
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in sorted(paths)
    }


def validate_capture(out, capture_pin, *, protocol=None, case_pin=None, role=None):
    cap = AIReviewCapture.model_validate_json(read_pin(out, capture_pin))
    req = AIReviewRequest.model_validate_json(read_pin(out, cap.request))
    events = AIHostSessionEvents.model_validate_json(read_pin(out, cap.host_events))
    final_raw = read_pin(out, cap.exact_final)
    final = AIReviewResponse.model_validate_json(final_raw)
    frozen = AIReviewProtocol.model_validate_json(read_pin(out, req.protocol))
    spec = AICaseSpec.model_validate_json(read_pin(out, req.case_input))
    if (
        req.case_input not in frozen.case_inputs
        or req.case_id != spec.case_id
        or req.reviewer not in frozen.reviewers
        or events.reviewer != req.reviewer
        or final.case_id != req.case_id
        or final.role != req.reviewer.role
        or req.response_schema_sha256 != response_schema_sha256()
        or frozen.response_schema_sha256 != response_schema_sha256()
        or cap.request_sha256 != model_sha256(req)
        or events.request_sha256 != cap.request_sha256
        or events.final_sha256 != cap.exact_final.sha256
    ):
        raise ValueError("sealed capture identity/schema binding differs")
    if not frozen.frozen_at < events.started_at < events.completed_at:
        raise ValueError("sealed capture completion timing differs")
    if protocol is not None and req.protocol != protocol:
        raise ValueError("sealed capture protocol differs")
    if case_pin is not None and req.case_input != case_pin:
        raise ValueError("sealed capture case differs")
    if role is not None and req.reviewer.role != role:
        raise ValueError("sealed capture role differs")
    read_pin(out, req.prompt)
    read_pin(out, events.raw_transcript)
    required = (*spec.source_evidence, spec.regulation_evidence, *spec.fixture_evidence)
    for pin in required:
        read_pin(out, pin)
    expected = set(required)
    allowed = (expected, expected | set(req.prior_responses))
    if (
        len(final.evidence) != len(set(final.evidence))
        or set(final.evidence) not in allowed
    ):
        raise ValueError("sealed response does not bind exact visible evidence")
    for prior in req.prior_responses:
        read_pin(out, prior)
    return cap, req, events, final_raw


def qualified(out, qualification_path):
    path = (
        out / qualification_path
        if not Path(qualification_path).is_absolute()
        else Path(qualification_path)
    )
    try:
        name = path.resolve().relative_to(out.resolve()).as_posix()
        receipt_pin = pin_file(out, name)
        receipt = json.loads(read_pin(out, receipt_pin))
        if receipt["status"] != "SEALED_AND_REPLAYED":
            raise ValueError("qualification is not sealed and replayed")
        identity = AIReviewerIdentity(
            role="ai_primary", model="gpt-6.1-sol", reasoning="medium"
        )
        if AIReviewerIdentity.model_validate(receipt["reviewer"]) != identity:
            raise ValueError("qualification reviewer differs")
        cap, req, event, _ = validate_capture(
            out, receipt["capture"], role="ai_primary"
        )
        if req.case_id != "migration_qualification_transport":
            raise ValueError(
                "qualification must be synthetic and outside official cases"
            )
        if req.reviewer != identity:
            raise ValueError("qualification request identity differs")
        for field, actual in (
            ("request", cap.request),
            ("host_events", cap.host_events),
            ("exact_final", cap.exact_final),
            ("raw_transcript", event.raw_transcript),
        ):
            if MigrationEvidencePin.model_validate(receipt[field]) != actual:
                raise ValueError("qualification receipt graph differs")
        launch = json.loads(read_pin(out, receipt["launch_receipt"]))
        launch_path = Path(cap.request.path).parent / "launch.txt"
        launch_pin = pin_file(out, launch_path.as_posix())
        read_pin(out, launch_pin)
        if (
            launch.get("transport") != "collaboration.spawn_agent"
            or launch.get("fork_turns") != "none"
            or launch.get("task_id") != event.task_id
            or launch.get("returned_task_name") != event.task_id
            or launch.get("request_sha256") != model_sha256(req)
            or launch.get("request_artifact_sha256") != cap.request.sha256
            or launch.get("launch_sha256") != launch_pin.sha256
        ):
            raise ValueError("qualification launch receipt binding differs")
        return receipt_pin
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"valid sealed qualification required: {error}") from error


def verified_inputs(root, out):
    prep = json.loads((out / "input-preparation.json").read_bytes())
    pins = tuple(MigrationEvidencePin.model_validate(p) for p in prep["case_inputs"])
    if (
        prep["candidate_count"] != 12
        or len(pins) != 12
        or prep.get("hidden_metadata_supplied") is not False
        or prep.get("generation_authorized") is not False
    ):
        raise ValueError("expected exact twelve unpromoted review inputs")
    manifest_raw = (out / "candidate-manifest.json").read_bytes()
    if manifest_raw != (root / "data/migration/candidate-manifest.json").read_bytes():
        raise ValueError("candidate manifest differs")
    manifest = json.loads(manifest_raw)
    for name, entry in manifest["files"].items():
        if (
            hashlib.sha256((root / "data/migration" / name).read_bytes()).hexdigest()
            != entry["sha256"]
        ):
            raise ValueError("candidate manifest artifact checksum differs")
    roster = [
        json.loads(line)
        for line in (root / "data/migration/candidate-roster.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    specifications = {
        item["case_id"]: item
        for item in (
            json.loads(line)
            for line in (root / "data/migration/oracle-candidate-specs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    }
    candidate_by_id = {item["case_id"]: item for item in roster}
    cases = []
    for pin in pins:
        raw = read_pin(out, pin)
        visible(json.loads(raw))
        spec = AICaseSpec.model_validate_json(raw)
        candidate = candidate_by_id.get(spec.case_id)
        authored = specifications.get(spec.case_id)
        if candidate is None or authored is None:
            raise ValueError("case absent from candidate manifest")
        body = spec.model_dump(mode="json")
        candidate_fields = (
            "instance_id",
            "drift_type",
            "stratum",
            "validation_capability",
            "primary_program",
            "frozen_sources",
        )
        authored_fields = (
            "allowed_source_scope",
            "intended_behavior",
            "unaffected_regressions",
            "affected_hosts",
        )
        if (
            any(body[name] != candidate[name] for name in candidate_fields)
            or any(body[name] != authored[name] for name in authored_fields)
            or spec.source_bundle_group != candidate["source_bundle_sha256"]
        ):
            raise ValueError("case source/scope/behavior differs from frozen candidate")
        for evidence in (
            *spec.source_evidence,
            spec.regulation_evidence,
            *spec.fixture_evidence,
        ):
            content = read_pin(out, evidence)
            if evidence.path.endswith(".json"):
                visible(json.loads(content))
        for frozen, evidence in zip(
            spec.frozen_sources, spec.source_evidence, strict=True
        ):
            if Path(evidence.path).name != Path(frozen.path).name:
                raise ValueError("source evidence path differs from frozen source")
        cases.append(spec)
    if (
        tuple(c.case_id for c in cases) != tuple(c["case_id"] for c in roster)
        or len({c.case_id for c in cases}) != 12
        or len(set(pins)) != 12
    ):
        raise ValueError("case inputs differ from exact candidate order")
    return pins, tuple(cases)


def packet(out, spec, role, prior=()):
    required = (*spec.source_evidence, spec.regulation_evidence, *spec.fixture_evidence)
    result = {
        "purpose": "Nonhuman migration review only; not patch generation or evaluation promotion.",
        "case": spec.model_dump(mode="json"),
        "role": role,
        "evidence": [
            {
                "pin": p.model_dump(),
                "exact_utf8_content": read_pin(out, p).decode("utf-8"),
            }
            for p in required
        ],
        "response_schema": AIReviewResponse.model_json_schema(),
        "instructions": (
            "Read only this single-case packet. Do not inspect repository history, other cases, other reviews, "
            "or hidden benchmark metadata. Do not write files, propose a patch, spawn agents, or call providers. "
            "Independently assess actual source and clause, allowed scope, intended regulatory behavior, "
            "concrete intended and unaffected regression fixtures, boundary coverage, validation capability "
            "and its limitations, and repeated-source dependence. The proposed class, behavior and fixtures "
            "are hypotheses; reject unsupported claims. Empty or unavailable fixture checks are not passes. "
            "Require a defensible justification for repeated-source pairs; dependence must remain disclosed. "
            "Return only one JSON object matching the exact response schema, the supplied case_id and role, "
            "and every exact source, regulation and fixture evidence pin. Include, exclude or needs_revision "
            "are valid judgments. Do not assert human identity or measured provider usage."
        ),
    }
    if role == "ai_adjudicator":
        result["prior_responses"] = [
            {
                "pin": p.model_dump(),
                "exact_utf8_content": read_pin(out, p).decode("utf-8"),
            }
            for p in prior
        ]
        result["instructions"] += (
            " Adjudicate the two retained independent finals and explain disagreements; preserve unresolved issues."
        )
    return result


def materialize(
    out, spec, case_pin, protocol_pin, reviewer, prior=(), completed_after=None
):
    base = f"requests/{spec.case_id}/{reviewer.role}"
    prompt_pin = save(
        out, f"{base}/prompt.json", packet(out, spec, reviewer.role, prior)
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


AMENDMENT_SOURCES = {
    "src/cobol_archaeologist/migration/ai_review.py",
    "scripts/seal_r2_review_session.py",
    "scripts/prepare_r2_reviews.py",
    "scripts/promote_r2_review_roster.py",
}


def check_runtime_snapshot(out, manifest_pin, inventory_pin, expected):
    manifest = json.loads(read_pin(out, manifest_pin))
    if (
        manifest.get("schema_version") != "migration-ai-review-runtime-snapshot-v1"
        or MigrationEvidencePin.model_validate(manifest["inventory"]) != inventory_pin
    ):
        raise ValueError("capture amendment runtime snapshot identity differs")
    files = manifest["files"]
    listed = (
        {item["path"]: item["sha256"] for item in files}
        if isinstance(files, list)
        else files
    )
    if listed != expected or (isinstance(files, list) and len(files) != len(listed)):
        raise ValueError("capture amendment snapshot file inventory differs")
    archive = MigrationEvidencePin.model_validate(manifest["archive"])
    read_pin(out, archive)
    with zipfile.ZipFile(out / archive.path) as bundle:
        if len(bundle.namelist()) != len(expected) or set(bundle.namelist()) != set(
            expected
        ):
            raise ValueError("capture amendment archive member inventory differs")
        for name, digest in expected.items():
            if hashlib.sha256(bundle.read(name)).hexdigest() != digest:
                raise ValueError("capture amendment archive source checksum differs")


def resume_runtime_pin(root, out, current):
    path = out / "runtime-source-inventory.json"
    if not path.exists():
        if (out / "review-capture-amendment.json").exists():
            raise ValueError("capture amendment requires original frozen runtime")
        return save(out, "runtime-source-inventory.json", current)
    original_pin = pin_file(out, "runtime-source-inventory.json")
    original = json.loads(read_pin(out, original_pin))
    amendment_path = out / "review-capture-amendment.json"
    if not amendment_path.exists():
        if path.read_bytes() != encoded(current):
            raise ValueError(
                "runtime source inventory changed after freeze; explicit capture amendment required"
            )
        return original_pin
    try:
        amendment = json.loads(
            read_pin(out, pin_file(out, "review-capture-amendment.json"))
        )
        protocol_pin = pin_file(out, "review-protocol.json")
        protocol = AIReviewProtocol.model_validate_json(read_pin(out, protocol_pin))
        if (
            amendment.get("schema_version")
            != "migration-ai-review-capture-amendment-v1"
            or amendment.get("reason") != "exact_prior_final_citation_gate_correction"
            or amendment.get("semantic_decisions_unchanged") is not True
            or amendment.get("request_input_schema_hashes_unchanged") is not True
            or MigrationEvidencePin.model_validate(amendment["protocol"])
            != protocol_pin
            or MigrationEvidencePin.model_validate(
                amendment["original_runtime_inventory"]
            )
            != original_pin
            or protocol.runtime_source_sha256 != original_pin.sha256
        ):
            raise ValueError(
                "unapproved capture amendment or original runtime/protocol binding differs"
            )
        amended_pin = MigrationEvidencePin.model_validate(
            amendment["amended_runtime_inventory"]
        )
        amended_raw = read_pin(out, amended_pin)
        amended = json.loads(amended_raw)
        if amended_raw != encoded(current) or set(original) != set(amended):
            raise ValueError("capture amendment current runtime inventory differs")
        changed = [
            {"path": name, "old_sha256": original[name], "new_sha256": amended[name]}
            for name in sorted(original)
            if original[name] != amended[name]
        ]
        if (
            not changed
            or amendment["changed_sources"] != changed
            or any(item["path"] not in AMENDMENT_SOURCES for item in changed)
        ):
            raise ValueError("capture amendment changes exceed authorized source scope")
        check_runtime_snapshot(
            out, amendment["original_runtime_snapshot_manifest"], original_pin, original
        )
        check_runtime_snapshot(
            out, amendment["amended_runtime_snapshot_manifest"], amended_pin, amended
        )
        bindings = amendment["unchanged_bindings"]
        if (
            MigrationEvidencePin.model_validate(bindings["protocol"]) != protocol_pin
            or bindings["response_schema_sha256"] != protocol.response_schema_sha256
            or protocol.response_schema_sha256 != response_schema_sha256()
            or tuple(
                MigrationEvidencePin.model_validate(item)
                for item in bindings["case_inputs"]
            )
            != protocol.case_inputs
        ):
            raise ValueError("capture amendment changed frozen input/schema bindings")
        for case_pin in protocol.case_inputs:
            read_pin(out, case_pin)
        seen = set()
        for item in bindings["requests"]:
            request_pin = MigrationEvidencePin.model_validate(item["request"])
            request = AIReviewRequest.model_validate_json(read_pin(out, request_pin))
            if (
                request_pin.path in seen
                or request.protocol != protocol_pin
                or request.case_input not in protocol.case_inputs
                or request.reviewer not in protocol.reviewers
                or request.response_schema_sha256 != protocol.response_schema_sha256
                or item["request_sha256"] != model_sha256(request)
            ):
                raise ValueError("capture amendment changed frozen request binding")
            spec = AICaseSpec.model_validate_json(read_pin(out, request.case_input))
            expected_path = (
                f"requests/{spec.case_id}/{request.reviewer.role}/request.json"
            )
            if request.case_id != spec.case_id or request_pin.path != expected_path:
                raise ValueError("capture amendment request path/case differs")
            read_pin(out, request.prompt)
            seen.add(request_pin.path)
        required = {
            f"requests/{AICaseSpec.model_validate_json(read_pin(out, p)).case_id}/{role}/request.json"
            for p in protocol.case_inputs
            for role in ROLES[:2]
        }
        if not required <= seen:
            raise ValueError("capture amendment omits frozen blind requests")
        return original_pin
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as error:
        raise ValueError(f"invalid review capture amendment: {error}") from error


def prepare(root: Path = ROOT, *, qualification_path=QUALIFICATION, frozen_at=None):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    qualification_pin = qualified(out, qualification_path)
    pins, cases = verified_inputs(root, out)
    runtime = inventory(root)
    runtime_pin = resume_runtime_pin(root, out, runtime)
    authorization = pin_file(out, "authorization.json")
    read_pin(out, authorization)
    manifest = pin_file(out, "candidate-manifest.json")
    existing = out / "review-protocol.json"
    frozen_time = (
        AIReviewProtocol.model_validate_json(existing.read_bytes()).frozen_at
        if existing.exists() and frozen_at is None
        else timestamp(frozen_at)
    )
    save(out, "response-schema.json", AIReviewResponse.model_json_schema())
    protocol = AIReviewProtocol(
        frozen_at=frozen_time,
        authorization_evidence=authorization,
        candidate_manifest=manifest,
        runtime_source_sha256=runtime_pin.sha256,
        response_schema_sha256=response_schema_sha256(),
        case_inputs=pins,
        reviewers=[
            AIReviewerIdentity(role=r, model="gpt-6.1-sol", reasoning="medium")
            for r in ROLES
        ],
    )
    proto_pin = save(out, "review-protocol.json", protocol)
    save(
        out,
        "review-preparation.json",
        {
            "status": "FROZEN_REVIEW_REQUESTS_ONLY",
            "protocol": proto_pin.model_dump(),
            "qualification": qualification_pin.model_dump(),
            "input_preparation": pin_file(out, "input-preparation.json").model_dump(),
            "runtime_inventory": runtime_pin.model_dump(),
            "case_count": 12,
            "blind_request_count": 24,
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
    case_id: str,
    *,
    root: Path = ROOT,
    captures=None,
    materialized_at=None,
    qualification_path=QUALIFICATION,
):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    protocol = prepare(root, qualification_path=qualification_path)
    proto_pin = pin_file(out, "review-protocol.json")
    cases = {
        AICaseSpec.model_validate_json(read_pin(out, pin)).case_id: pin
        for pin in protocol.case_inputs
    }
    if case_id not in cases:
        raise ValueError("unknown frozen case")
    case_pin = cases[case_id]
    if captures is None:
        try:
            captures = [
                pin_file(out, f"captures/{case_id}/{role}.json") for role in ROLES[:2]
            ]
        except OSError as error:
            raise ValueError("both sealed independent captures required") from error
    if len(captures) != 2:
        raise ValueError("both sealed independent captures required")
    validated = [
        validate_capture(out, pin, protocol=proto_pin, case_pin=case_pin, role=role)
        for pin, role in zip(captures, ROLES[:2], strict=True)
    ]
    if (
        validated[0][2].task_id == validated[1][2].task_id
        or validated[0][2].session_id == validated[1][2].session_id
    ):
        raise ValueError("independent captures reused session/task")
    completed = max(row[2].completed_at for row in validated)
    if timestamp(materialized_at) <= completed:
        raise ValueError(
            "adjudicator cannot materialize before both captures completed"
        )
    prior = tuple(row[0].exact_final for row in validated)
    spec = AICaseSpec.model_validate_json(read_pin(out, case_pin))
    return materialize(
        out,
        spec,
        case_pin,
        proto_pin,
        protocol.reviewers[2],
        prior,
        completed.isoformat(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--qualification", default=QUALIFICATION)
    parser.add_argument("--adjudicator", metavar="CASE_ID")
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
        protocol = prepare(args.root, qualification_path=args.qualification)
        print(
            json.dumps(
                {
                    "case_count": len(protocol.case_inputs),
                    "provider_calls": 0,
                    "generation_authorized": False,
                }
            )
        )


if __name__ == "__main__":
    main()
