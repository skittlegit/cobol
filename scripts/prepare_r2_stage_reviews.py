"""Freeze additive, stage-aware blind reviews without changing prior evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICaseSpec,
    AIReviewerIdentity,
    AIReviewProtocol,
    AIReviewResponse,
)
from cobol_archaeologist.migration.contracts import MigrationEvidencePin

ROOT = Path(__file__).resolve().parents[1]


def helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


original = helper("prepare_r2_reviews")
revisions = helper("prepare_r2_revision_reviews")
promoter = helper("promote_r2_review_revisions")
contracts = helper("stage_review_contracts")
CASE_IDS = revisions.CASE_IDS
QUALIFICATION = original.QUALIFICATION
AUTHORIZATION = "stage-review/authorization.json"
STAGE_SCRIPTS = (
    "scripts/stage_review_contracts.py",
    "scripts/prepare_r2_stage_reviews.py",
    "scripts/seal_r2_stage_review_session.py",
    "scripts/promote_r2_stage_review_roster.py",
)
save, read_pin, pin_file = original.save, original.read_pin, original.pin_file


def authorization(out, name=AUTHORIZATION):
    pin = pin_file(out, name)
    body = json.loads(read_pin(out, pin))
    if (
        body.get("authorized") is not True
        or body.get("scope") != "prospective_stage_aware_review"
    ):
        raise ValueError("explicit prospective stage-review authorization required")
    proposal = MigrationEvidencePin.model_validate(body["proposal"])
    root = out.parents[2]
    read_pin(root, proposal)
    if (
        proposal.path
        != "data/migration/coordination/proposed-stage-review-amendment.json"
    ):
        raise ValueError("authorization must bind the approved stage-review proposal")
    return pin


def audit_history(root, out):
    """Read and replay all 48 prior captures, their receipts and real baseline."""
    contexts = (set(), set())
    proto = AIReviewProtocol.model_validate_json(
        (out / "review-protocol.json").read_bytes()
    )
    ids = tuple(
        AICaseSpec.model_validate_json(read_pin(out, p)).case_id
        for p in proto.case_inputs
    )
    if len(ids) != 12 or len(set(ids)) != 12:
        raise ValueError("exact twelve original cases required")
    intake = promoter.OLD.prerequisites(root, out, proto, ids)
    old = promoter.collect(out, "review-protocol.json", "", ids, contexts)
    receipt_pin, _, original_cases, _ = revisions.original_receipt(out)
    receipt = json.loads(read_pin(out, receipt_pin))
    if (
        receipt["reviews"] != old[5]
        or old[4].accepted_case_ids
        or tuple(receipt.get("accepted_original_case_ids", ()))
        != old[4].accepted_case_ids
    ):
        raise ValueError("original receipt differs or authorizes unexpected cases")
    new = promoter.collect(
        out, "revisions/review-protocol.json", "revisions/", CASE_IDS, contexts
    )
    rev_receipt_pin = pin_file(out, "revisions/review-receipt.json")
    revised_receipt = json.loads(read_pin(out, rev_receipt_pin))
    if (
        revised_receipt.get("schema_version") != "migration-revised-review-receipt-v1"
        or revised_receipt.get("status") != "COMPLETE_12_REVIEWED_GATE_STAGE_MISMATCH"
        or revised_receipt.get("capture_count") != 12
        or revised_receipt.get("total_original_and_revision_captures") != 48
        or revised_receipt.get("all_task_and_session_contexts_distinct") is not True
        or revised_receipt.get("reviews") != new[5]
        or MigrationEvidencePin.model_validate(revised_receipt["review_protocol"])
        != new[0]
    ):
        raise ValueError("all twelve revised receipt bindings required")
    prep_pin, pins, specs = revisions.verified_inputs(out, original_cases)
    if pins != new[1].case_inputs or specs != new[2]:
        raise ValueError("revised case inputs changed after freeze")
    originals = {s.case_id: s for s in old[2]}
    for spec in specs:
        promoter.check_revision(originals[spec.case_id], spec)
    baseline = promoter.revised_baseline(out, specs, original_cases)
    runtime_manifest = promoter.runtime(root, out, new[1])
    if (
        MigrationEvidencePin.model_validate(revised_receipt["runtime_manifest"])
        != runtime_manifest
    ):
        raise ValueError("revised receipt runtime snapshot differs")
    if (
        new[1].frozen_at <= old[7]
        or new[1].candidate_manifest != old[1].candidate_manifest
    ):
        raise ValueError("revised protocol freshness or intake differs")
    if len(contexts[0]) != 48 or len(contexts[1]) != 48:
        raise ValueError("all 48 distinct historical contexts required")
    return {
        "case_ids": CASE_IDS,
        "specs": specs,
        "case_pins": pins,
        "protocol": new[1],
        "records": old[5] + new[5],
        "capture_count": 48,
        "task_ids": sorted(contexts[0]),
        "session_ids": sorted(contexts[1]),
        "completed_at": max(old[7], new[7]),
        "original_receipt": receipt_pin,
        "revision_receipt": rev_receipt_pin,
        "input_preparation": prep_pin,
        "baseline": baseline,
        "runtime_manifest": runtime_manifest,
        "intake": intake,
    }


def inherited_packet(out, case_id, records):
    issues, finals = [], []
    for row in records:
        if row["case_id"] != case_id:
            continue
        cap, _, _, raw = original.validate_capture(
            out, row["capture"], role=row["role"]
        )
        response = AIReviewResponse.model_validate_json(raw)
        finals.append(cap.exact_final)
        for index, text in enumerate(response.unresolved_issues):
            issues.append(
                contracts.StageInheritedIssue(
                    index=len(issues),
                    text=text,
                    final_pin=cap.exact_final,
                    final_issue_index=index,
                )
            )
    return contracts.StageInheritedIssuePacket(
        case_id=case_id, issues=tuple(issues), historical_finals=tuple(finals)
    )


def runtime_inventory(root, out):
    old_pin = pin_file(out, "revisions/runtime-source-inventory.json")
    inventory = json.loads(read_pin(out, old_pin))
    if len(inventory) != 112:
        raise ValueError("exact 112-file prior runtime inventory required")
    for name, digest in inventory.items():
        read_pin(root, {"path": name, "sha256": digest})
    # DECISION: Explicit additive scripts preserve the frozen source membership.
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in sorted(set(inventory) | set(STAGE_SCRIPTS))
    }


def snapshot(root, out, inventory, inventory_pin):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as bundle:
        for name, digest in sorted(inventory.items()):
            raw = (root / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("runtime source changed while snapshotting")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, raw)
    archive = save(out, "stage-review/runtime-source.zip", stream.getvalue())
    manifest = save(
        out,
        "stage-review/runtime-source-manifest.json",
        {
            "schema_version": "migration-ai-review-runtime-snapshot-v1",
            "inventory": inventory_pin.model_dump(),
            "archive": archive.model_dump(),
            "files": inventory,
        },
    )
    original.check_runtime_snapshot(out, manifest, inventory_pin, inventory)
    return manifest


def packet(out, spec, role, inherited, prior=()):
    required = (*spec.source_evidence, spec.regulation_evidence, *spec.fixture_evidence)
    result = original.packet(out, spec, role, ())
    result["response_schema"] = contracts.StageReviewResponse.model_json_schema()
    # DECISION: Original pin paths reveal old reviewer roles. Keep them in the
    # bound audit inventory; expose only opaque origin digests to blind reviewers.
    result["inherited_issues"] = [
        {
            "index": issue.index,
            "text": issue.text,
            "origin": "origin-" + issue.final_pin.sha256[:16],
            "original_final_sha256": issue.final_pin.sha256,
            "final_issue_index": issue.final_issue_index,
        }
        for issue in inherited.issues
    ]
    result["evidence"] = [
        {
            "pin": p.model_dump(),
            "exact_utf8_content": read_pin(out, p).decode("utf-8"),
        }
        for p in required
    ]
    result["instructions"] = (
        "Nonhuman prospective stage-aware selection review. Read this packet only. "
        "Independently assess actual frozen source, exact regulation, allowed scope, concrete intended "
        "and unaffected regression fixtures, actual original execution and qualified capability. "
        "Proposed claims are hypotheses. Classify EVERY indexed inherited issue, preserving its exact text "
        "and inherited_issue_index, with a source-grounded rationale and verbatim quoted pinned evidence. "
        "Repeat each inherited classification unchanged in its matching typed category array as well "
        "as inherited_issue_classifications, in index order. "
        "Use pre_generation_blocker, scope_limitation, post_patch_validation_obligation, or "
        "historical_evidence_qualification; do not classify by keywords or discard an issue. "
        "Historical origin IDs carry no reviewer decision or authority. Report any new concerns in the "
        "four typed category arrays; unresolved_issues must be empty because all issues are typed. "
        "A missing required affected host, unsupported regulation, insufficient scope, empty/unavailable "
        "required fixtures, missing compiler identity or contradictory baseline is a selection blocker. "
        "Finite tests do not imply equivalence, universal compliance, untested host preservation or "
        "independent contribution. Preserve source_bundle_group dependence and finite scope. "
        "Post-generation scope/apply/parser/call-graph/dataflow/slice/compiler/intended/regression/fanout "
        "and source-binding checks remain mandatory later obligations; no patch exists yet. "
        "Include requires zero selection blockers, finite supported scope/fixtures/capability, explicit "
        "limitations and later obligations. Exclude and needs_revision remain valid. "
        "Do not inspect other files or history, write files, propose patches, call providers or spawn agents. "
        "Return only exact schema JSON with supplied case_id/role and every exact evidence pin."
    )
    result.pop("prior_responses", None)
    if role == ROLES[2]:
        if len(prior) != 2:
            raise ValueError("adjudicator requires exactly two fresh sealed finals")
        result["prior_responses"] = [
            {
                "pin": p.model_dump(),
                "exact_utf8_content": read_pin(out, p).decode("utf-8"),
            }
            for p in prior
        ]
        result["instructions"] += (
            " Adjudicate exactly the two supplied fresh finals, explain every disagreement and "
            "record each inherited classification disagreement resolved; preserve all substantive blockers."
        )
    elif prior:
        raise ValueError("blind stage reviews cannot receive prior finals")
    return result


def materialize(
    out,
    spec,
    case_pin,
    protocol_pin,
    reviewer,
    inherited_pin,
    prior=(),
    completed_after=None,
):
    inherited = contracts.StageInheritedIssuePacket.model_validate_json(
        read_pin(out, inherited_pin)
    )
    base = f"stage-review/requests/{spec.case_id}/{reviewer.role}"
    prompt = save(
        out, f"{base}/prompt.json", packet(out, spec, reviewer.role, inherited, prior)
    )
    request = contracts.StageReviewRequest(
        case_id=spec.case_id,
        reviewer=reviewer,
        protocol=protocol_pin,
        case_input=case_pin,
        prompt=prompt,
        inherited_issues=inherited_pin,
        response_schema_sha256=contracts.response_schema_sha256(),
        prior_responses=prior,
    )
    request_pin = save(out, f"{base}/request.json", request)
    launch = save(
        out,
        f"{base}/launch.txt",
        (
            f"Read only {(out / prompt.path).resolve().as_posix()} using a read-only command. "
            "Do not inspect other files, history, cases or reviews; do not write, patch, call providers or spawn agents. "
            "Follow the packet and return only exact JSON. Fresh nonhuman collaboration subagent: "
            "fork_turns none, gpt-6.1-sol medium."
        ).encode(),
    )
    save(
        out,
        f"{base}/launch-contract.json",
        {
            "request": request_pin.model_dump(),
            "request_sha256": contracts.model_sha256(request),
            "prompt": prompt.model_dump(),
            "launch": launch.model_dump(),
            "reviewer": reviewer.model_dump(mode="json"),
            "fork_turns": "none",
            "read_only": True,
            "not_before": completed_after,
            "provider_calls": 0,
        },
    )
    return request


def prepare(
    root=ROOT,
    *,
    qualification_path=QUALIFICATION,
    frozen_at=None,
    authorization_path=AUTHORIZATION,
):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    approval = authorization(out, authorization_path)
    qualified = original.qualified(out, qualification_path)
    audit = audit_history(root, out)
    inventory = runtime_inventory(root, out)
    existing = out / "stage-review/review-protocol.json"
    time = (
        contracts.StageReviewProtocol.model_validate_json(
            existing.read_bytes()
        ).frozen_at
        if existing.exists() and frozen_at is None
        else original.timestamp(frozen_at)
    )
    if time <= audit["completed_at"]:
        raise ValueError("stage freeze must follow all 48 historical completions")
    authorized_at = json.loads(read_pin(out, approval)).get("authorized_at")
    if authorized_at is not None and time <= original.timestamp(authorized_at):
        raise ValueError("stage freeze must prospectively follow authorization")
    inventory_pin = save(out, "stage-review/runtime-source-inventory.json", inventory)
    manifest = snapshot(root, out, inventory, inventory_pin)
    issue_pins = tuple(
        save(
            out,
            f"stage-review/inherited-issues/{s.case_id}.json",
            inherited_packet(out, s.case_id, audit["records"]),
        )
        for s in audit["specs"]
    )
    protocol = contracts.StageReviewProtocol(
        frozen_at=time,
        authorization_evidence=approval,
        candidate_manifest=audit["protocol"].candidate_manifest,
        runtime_source_sha256=inventory_pin.sha256,
        response_schema_sha256=contracts.response_schema_sha256(),
        case_inputs=audit["case_pins"],
        inherited_issue_packets=issue_pins,
        reviewers=[
            AIReviewerIdentity(role=r, model="gpt-6.1-sol", reasoning="medium")
            for r in ROLES
        ],
    )
    protocol_pin = save(out, "stage-review/review-protocol.json", protocol)
    save(
        out,
        "stage-review/response-schema.json",
        contracts.StageReviewResponse.model_json_schema(),
    )
    save(
        out,
        "stage-review/review-preparation.json",
        {
            "status": "FROZEN_STAGE_REVIEW_REQUESTS_ONLY",
            "protocol": protocol_pin.model_dump(),
            "qualification": qualified.model_dump(),
            "runtime_inventory": inventory_pin.model_dump(),
            "runtime_manifest": manifest.model_dump(),
            "authorization": approval.model_dump(),
            "original_review_receipt": audit["original_receipt"].model_dump(),
            "revision_review_receipt": audit["revision_receipt"].model_dump(),
            "input_preparation": audit["input_preparation"].model_dump(),
            "revised_original_baseline_qualification": audit["baseline"].model_dump(),
            "historical_capture_count": 48,
            "historical_task_ids": audit["task_ids"],
            "historical_session_ids": audit["session_ids"],
            "case_count": 4,
            "blind_request_count": 8,
            "adjudicator_requests_require_two_sealed_captures": True,
            "provider_calls": 0,
            "generation_authorized": False,
        },
    )
    for spec, case_pin, inherited in zip(
        audit["specs"], audit["case_pins"], issue_pins, strict=True
    ):
        for reviewer in protocol.reviewers[:2]:
            materialize(out, spec, case_pin, protocol_pin, reviewer, inherited)
    return protocol


def adjudicator(
    case_id,
    *,
    root=ROOT,
    captures=None,
    materialized_at=None,
    qualification_path=QUALIFICATION,
    authorization_path=AUTHORIZATION,
):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    protocol = prepare(
        root,
        qualification_path=qualification_path,
        authorization_path=authorization_path,
    )
    protocol_pin = pin_file(out, "stage-review/review-protocol.json")
    mapping = {
        AICaseSpec.model_validate_json(read_pin(out, p)).case_id: (p, i)
        for p, i in zip(
            protocol.case_inputs, protocol.inherited_issue_packets, strict=True
        )
    }
    if case_id not in mapping:
        raise ValueError("unknown frozen stage case")
    if captures is None:
        try:
            captures = [
                pin_file(out, f"stage-review/reviews/{case_id}/{r}/capture.json")
                for r in ROLES[:2]
            ]
        except OSError as error:
            raise ValueError("both sealed stage captures required") from error
    if len(captures) != 2:
        raise ValueError("both sealed stage captures required")
    sealer = helper("seal_r2_stage_review_session")
    case_pin, issues_pin = mapping[case_id]
    rows = [
        sealer.validate_capture(
            out, p, protocol=protocol_pin, case_pin=case_pin, role=r
        )
        for p, r in zip(captures, ROLES[:2], strict=True)
    ]
    if (
        rows[0][2].task_id == rows[1][2].task_id
        or rows[0][2].session_id == rows[1][2].session_id
    ):
        raise ValueError("independent stage contexts reused")
    completed = max(row[2].completed_at for row in rows)
    if original.timestamp(materialized_at) <= completed:
        raise ValueError("adjudicator must materialize after both sealed stage finals")
    return materialize(
        out,
        AICaseSpec.model_validate_json(read_pin(out, case_pin)),
        case_pin,
        protocol_pin,
        protocol.reviewers[2],
        issues_pin,
        tuple(row[0].exact_final for row in rows),
        completed.isoformat(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--qualification", default=QUALIFICATION)
    parser.add_argument("--authorization", default=AUTHORIZATION)
    parser.add_argument("--adjudicator")
    parser.add_argument("--primary-capture")
    parser.add_argument("--verifier-capture")
    args = parser.parse_args()
    options = {
        "root": args.root,
        "qualification_path": args.qualification,
        "authorization_path": args.authorization,
    }
    if args.adjudicator:
        captures = None
        if args.primary_capture or args.verifier_capture:
            if not (args.primary_capture and args.verifier_capture):
                parser.error("both capture paths are required")
            out = args.root / "data/migration/ai-review"
            captures = [
                pin_file(out, n) for n in (args.primary_capture, args.verifier_capture)
            ]
        result = adjudicator(args.adjudicator, captures=captures, **options)
    else:
        result = prepare(**options)
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
