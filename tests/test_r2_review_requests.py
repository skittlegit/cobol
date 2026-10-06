"""Frozen review packets must fail closed before any official reviewer launch."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location(
        "prepare_r2_reviews", ROOT / "scripts/prepare_r2_reviews.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def save(base, name, obj):
    raw = (
        obj
        if isinstance(obj, bytes)
        else (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode()
    )
    path = base / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    out = root / "data/migration/ai-review"
    out.mkdir(parents=True)
    source = ROOT / "data/migration/ai-review"
    shutil.copytree(source / "inputs", out / "inputs")
    for name in ("candidate-manifest.json", "input-preparation.json"):
        shutil.copyfile(source / name, out / name)
    for name in (
        "candidate-manifest.json",
        "candidate-roster.jsonl",
        "oracle-candidate-specs.jsonl",
        "detector-visible-candidates.jsonl",
    ):
        shutil.copyfile(ROOT / "data/migration" / name, root / "data/migration" / name)
    (root / "src").mkdir()
    (root / "src/demo.py").write_text("pass\n")
    (root / "scripts").mkdir()
    for name in module().RUNTIME_SCRIPTS:
        (root / name).write_text("pass\n")
    save(
        out,
        "authorization.json",
        {
            "user_authorization": "AI-primary independent AI verification and adjudication",
            "nonhuman": True,
        },
    )
    return root, out


def capture(builder, out, request, name, start, end):
    from cobol_archaeologist.migration.ai_review import (
        AIHostSessionEvents,
        AIReviewCapture,
        AIReviewResponse,
        model_sha256,
    )

    reqpin = {
        "path": name + "/request.json",
        "sha256": hashlib.sha256(
            (out / (name + "/request.json")).read_bytes()
        ).hexdigest(),
    }
    spec = builder.AICaseSpec.model_validate_json(
        builder.read_pin(out, request.case_input)
    )
    evidence = [*spec.source_evidence, spec.regulation_evidence, *spec.fixture_evidence]
    final = AIReviewResponse(
        case_id=spec.case_id,
        role=request.reviewer.role,
        decision="include",
        rationale="Review",
        scope_judgment="bounded",
        intended_fixture_judgment="concrete",
        regression_fixture_judgment="concrete",
        capability_judgment="finite",
        duplicate_source_judgment="dependent",
        evidence=evidence,
    )
    final_pin = save(out, name + "/final.json", final.model_dump(mode="json"))
    transcript = save(
        out, name + "/transcript.json", {"retained_host_transcript": True}
    )
    events = AIHostSessionEvents(
        provenance="host_captured_collaboration_session",
        task_id=name,
        session_id=name,
        reviewer=request.reviewer,
        request_sha256=model_sha256(request),
        final_sha256=final_pin["sha256"],
        started_at=start,
        completed_at=end,
        raw_transcript=transcript,
    )
    event_pin = save(out, name + "/events.json", events.model_dump(mode="json"))
    cap = AIReviewCapture(
        request=reqpin,
        request_sha256=model_sha256(request),
        exact_final=final_pin,
        host_events=event_pin,
    )
    cap_pin = save(out, name + "/capture.json", cap.model_dump(mode="json"))
    return cap_pin, event_pin, final_pin, reqpin, transcript


def qualification(builder, out):
    # Synthetic qualification is independently pinned and explicitly outside the roster.
    prep = json.loads((out / "input-preparation.json").read_bytes())
    case_pin = prep["case_inputs"][0]
    case = builder.AICaseSpec.model_validate_json(builder.read_pin(out, case_pin))
    case = case.model_copy(
        update={
            "case_id": "migration_qualification_transport",
            "instance_id": "drift_999999",
        }
    )
    case_pin = save(
        out, "qualification/transport-v1/case-input.json", case.model_dump(mode="json")
    )
    reviewer = builder.AIReviewerIdentity(
        role="ai_primary", model="gpt-6.1-sol", reasoning="medium"
    )
    protocol = builder.AIReviewProtocol(
        frozen_at="2026-10-05T00:00:00Z",
        authorization_evidence={
            "path": "authorization.json",
            "sha256": hashlib.sha256(
                (out / "authorization.json").read_bytes()
            ).hexdigest(),
        },
        candidate_manifest={
            "path": "candidate-manifest.json",
            "sha256": hashlib.sha256(
                (out / "candidate-manifest.json").read_bytes()
            ).hexdigest(),
        },
        runtime_source_sha256="a" * 64,
        response_schema_sha256=builder.response_schema_sha256(),
        case_inputs=[case_pin],
        reviewers=[
            builder.AIReviewerIdentity(role=r, model="gpt-6.1-sol", reasoning="medium")
            for r in builder.ROLES
        ],
    )
    proto_pin = save(
        out,
        "qualification/transport-v1/protocol.json",
        protocol.model_dump(mode="json"),
    )
    prompt_pin = save(
        out, "qualification/transport-v1/prompt.json", {"synthetic": True}
    )
    request = builder.AIReviewRequest(
        case_id=case.case_id,
        reviewer=reviewer,
        protocol=proto_pin,
        case_input=case_pin,
        prompt=prompt_pin,
        response_schema_sha256=builder.response_schema_sha256(),
    )
    save(
        out, "qualification/transport-v1/request.json", request.model_dump(mode="json")
    )
    pins = capture(
        builder,
        out,
        request,
        "qualification/transport-v1",
        "2026-10-05T01:00:00Z",
        "2026-10-05T02:00:00Z",
    )
    launch_bytes = save(
        out, "qualification/transport-v1/launch.txt", b"Frozen qualification launch"
    )
    from cobol_archaeologist.migration.ai_review import model_sha256

    launch = save(
        out,
        "qualification/transport-v1/launch-receipt.json",
        {
            "transport": "collaboration.spawn_agent",
            "fork_turns": "none",
            "task_id": "qualification/transport-v1",
            "returned_task_name": "qualification/transport-v1",
            "request_sha256": model_sha256(request),
            "request_artifact_sha256": pins[3]["sha256"],
            "launch_sha256": launch_bytes["sha256"],
        },
    )
    return save(
        out,
        "qualification/transport-v1/qualification-receipt.json",
        {
            "status": "SEALED_AND_REPLAYED",
            "reviewer": reviewer.model_dump(mode="json"),
            "capture": pins[0],
            "host_events": pins[1],
            "exact_final": pins[2],
            "request": pins[3],
            "raw_transcript": pins[4],
            "launch_receipt": launch,
        },
    )


def freeze(repository):
    root, out = repository
    builder = module()
    qualification(builder, out)
    protocol = builder.prepare(root, frozen_at="2026-10-06T00:00:00Z")
    return builder, root, out, protocol


def test_missing_qualification_refuses_official_packets(repository):
    builder = module()
    with pytest.raises(ValueError, match="qualification"):
        builder.prepare(repository[0])
    assert not (repository[1] / "review-protocol.json").exists()


def test_exact_order_and_blind_single_case_packets(repository):
    builder, _, out, protocol = freeze(repository)
    original = json.loads((out / "input-preparation.json").read_bytes())
    assert [p.model_dump() for p in protocol.case_inputs] == original["case_inputs"]
    assert len(protocol.case_inputs) == 12
    all_ids = [
        builder.AICaseSpec.model_validate_json(builder.read_pin(out, p)).case_id
        for p in protocol.case_inputs
    ]
    for case_id in all_ids:
        for role in builder.ROLES[:2]:
            request = builder.AIReviewRequest.model_validate_json(
                (out / f"requests/{case_id}/{role}/request.json").read_bytes()
            )
            packet = json.loads(builder.read_pin(out, request.prompt))
            assert not request.prior_responses
            assert packet["case"]["case_id"] == case_id
            text = json.dumps(packet)
            assert all(other not in text for other in all_ids if other != case_id)
            assert (
                packet["response_schema"]
                == builder.AIReviewResponse.model_json_schema()
            )
            for evidence in packet["evidence"]:
                assert evidence["exact_utf8_content"].encode() == builder.read_pin(
                    out, evidence["pin"]
                )
    assert not list(out.glob("requests/*/ai_adjudicator/request.json"))


@pytest.mark.parametrize(
    "kind", ["source_evidence", "regulation_evidence", "fixture_evidence"]
)
def test_tampered_case_evidence_rejected_before_freeze(repository, kind):
    builder = module()
    root, out = repository
    qualification(builder, out)
    pin = json.loads((out / "input-preparation.json").read_bytes())["case_inputs"][1]
    case = json.loads(builder.read_pin(out, pin))
    evidence = case[kind] if kind == "regulation_evidence" else case[kind][0]
    (out / evidence["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        builder.prepare(root)
    assert not (out / "review-protocol.json").exists()


def test_immutable_overwrite_and_runtime_change_rejected(repository):
    builder, root, out, protocol = freeze(repository)
    assert builder.prepare(root) == protocol
    with pytest.raises(ValueError, match="immutable"):
        builder.immutable_bytes(out / "review-protocol.json", b"replacement")
    (root / "src/demo.py").write_text("changed\n")
    with pytest.raises(ValueError, match="runtime"):
        builder.prepare(root)


def test_adjudication_requires_completed_exact_sealed_prior_finals(repository):
    builder, root, out, protocol = freeze(repository)
    case = builder.AICaseSpec.model_validate_json(
        builder.read_pin(out, protocol.case_inputs[0])
    )
    with pytest.raises(ValueError, match="capture"):
        builder.adjudicator(case.case_id, root=root)
    caps = []
    for role in builder.ROLES[:2]:
        name = f"requests/{case.case_id}/{role}"
        request = builder.AIReviewRequest.model_validate_json(
            (out / name / "request.json").read_bytes()
        )
        caps.append(
            capture(
                builder,
                out,
                request,
                name,
                "2026-10-06T01:00:00Z",
                "2026-10-06T02:00:00Z",
            )[0]
        )
    with pytest.raises(ValueError, match="completed"):
        builder.adjudicator(
            case.case_id,
            root=root,
            captures=caps,
            materialized_at="2026-10-06T01:30:00Z",
        )
    request = builder.adjudicator(
        case.case_id, root=root, captures=caps, materialized_at="2026-10-06T03:00:00Z"
    )
    assert len(request.prior_responses) == 2
    packet = json.loads(builder.read_pin(out, request.prompt))
    for prior in packet["prior_responses"]:
        assert prior["exact_utf8_content"].encode() == builder.read_pin(
            out, prior["pin"]
        )
    (out / request.prior_responses[0].path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="checksum"):
        builder.adjudicator(case.case_id, root=root, captures=caps)


def test_rehashed_hidden_metadata_is_refused(repository):
    builder = module()
    root, out = repository
    qualification(builder, out)
    prep = json.loads((out / "input-preparation.json").read_bytes())
    pin = prep["case_inputs"][0]
    case = json.loads(builder.read_pin(out, pin))
    case["labels"] = ["hidden"]
    prep["case_inputs"][0] = save(out, pin["path"], case)
    save(out, "input-preparation.json", prep)
    with pytest.raises(ValueError, match="hidden metadata"):
        builder.prepare(root)


def test_rehashed_qualification_launch_identity_tamper_is_refused(repository):
    builder = module()
    root, out = repository
    qpin = qualification(builder, out)
    receipt = json.loads(builder.read_pin(out, qpin))
    launch = json.loads(builder.read_pin(out, receipt["launch_receipt"]))
    launch["fork_turns"] = "all"
    receipt["launch_receipt"] = save(out, receipt["launch_receipt"]["path"], launch)
    save(out, qpin["path"], receipt)
    with pytest.raises(ValueError, match="qualification launch"):
        builder.prepare(root)


def test_rehashed_scope_change_cannot_replace_candidate_contract(repository):
    builder = module()
    root, out = repository
    qualification(builder, out)
    prep = json.loads((out / "input-preparation.json").read_bytes())
    pin = prep["case_inputs"][0]
    case = json.loads(builder.read_pin(out, pin))
    case["allowed_source_scope"][0]["line_spans"] = [[1, 100]]
    prep["case_inputs"][0] = save(out, pin["path"], case)
    save(out, "input-preparation.json", prep)
    with pytest.raises(ValueError, match="scope/behavior"):
        builder.prepare(root)


def test_duplicate_response_evidence_rejected_after_outer_repins(repository):
    builder, _root, out, protocol = freeze(repository)
    case = builder.AICaseSpec.model_validate_json(
        builder.read_pin(out, protocol.case_inputs[0])
    )
    name = f"requests/{case.case_id}/{builder.ROLES[0]}"
    request = builder.AIReviewRequest.model_validate_json(
        (out / name / "request.json").read_bytes()
    )
    cap_pin, event_pin, final_pin, _, _ = capture(
        builder, out, request, name, "2026-10-06T01:00:00Z", "2026-10-06T02:00:00Z"
    )
    final = json.loads(builder.read_pin(out, final_pin))
    final["evidence"].append(final["evidence"][0])
    final_pin = save(out, final_pin["path"], final)
    events = json.loads(builder.read_pin(out, event_pin))
    events["final_sha256"] = final_pin["sha256"]
    event_pin = save(out, event_pin["path"], events)
    cap = json.loads(builder.read_pin(out, cap_pin))
    cap["host_events"] = event_pin
    cap["exact_final"] = final_pin
    cap_pin = save(out, cap_pin["path"], cap)
    with pytest.raises(ValueError, match="exact visible evidence"):
        builder.validate_capture(out, cap_pin)


def runtime_snapshot(builder, root, out, prefix, inventory):
    import zipfile

    inventory_pin = save(out, prefix + "runtime-source-inventory.json", inventory)
    archive_path = out / (prefix + "runtime-source.zip")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name in inventory:
            archive.write(root / name, name)
    archive_pin = builder.pin_file(out, prefix + "runtime-source.zip")
    manifest_pin = save(
        out,
        prefix + "runtime-source-manifest.json",
        {
            "schema_version": "migration-ai-review-runtime-snapshot-v1",
            "inventory": inventory_pin,
            "archive": archive_pin.model_dump(),
            "files": [
                {"path": name, "sha256": digest} for name, digest in inventory.items()
            ],
        },
    )
    return inventory_pin, manifest_pin


def amend_runtime(builder, root, out, protocol):
    original = json.loads((out / "runtime-source-inventory.json").read_bytes())
    original_pin, original_manifest = runtime_snapshot(builder, root, out, "", original)
    changed = "scripts/prepare_r2_reviews.py"
    (root / changed).write_text("# explicit capture citation gate correction\npass\n")
    current = builder.inventory(root)
    current_pin, current_manifest = runtime_snapshot(
        builder, root, out, "capture-gate-amendment/", current
    )
    protocol_pin = builder.pin_file(out, "review-protocol.json").model_dump()
    from cobol_archaeologist.migration.ai_review import model_sha256

    requests = []
    for path in sorted((out / "requests").rglob("request.json")):
        request_pin = builder.pin_file(out, path.relative_to(out).as_posix())
        request = builder.AIReviewRequest.model_validate_json(
            builder.read_pin(out, request_pin)
        )
        requests.append(
            {
                "request": request_pin.model_dump(),
                "request_sha256": model_sha256(request),
            }
        )
    amendment = {
        "schema_version": "migration-ai-review-capture-amendment-v1",
        "protocol": protocol_pin,
        "original_runtime_inventory": original_pin,
        "original_runtime_snapshot_manifest": original_manifest,
        "amended_runtime_inventory": current_pin,
        "amended_runtime_snapshot_manifest": current_manifest,
        "reason": "exact_prior_final_citation_gate_correction",
        "semantic_decisions_unchanged": True,
        "request_input_schema_hashes_unchanged": True,
        "changed_sources": [
            {
                "path": changed,
                "old_sha256": original[changed],
                "new_sha256": current[changed],
            }
        ],
        "unchanged_bindings": {
            "protocol": protocol_pin,
            "response_schema_sha256": protocol.response_schema_sha256,
            "case_inputs": [pin.model_dump() for pin in protocol.case_inputs],
            "requests": requests,
        },
    }
    save(out, "review-capture-amendment.json", amendment)
    return amendment


def test_explicit_capture_amendment_preserves_original_protocol_and_packets(repository):
    builder, root, out, protocol = freeze(repository)
    frozen_protocol = (out / "review-protocol.json").read_bytes()
    requests = {
        path.relative_to(out).as_posix(): path.read_bytes()
        for path in (out / "requests").rglob("*")
        if path.is_file()
    }
    original_inventory = (out / "runtime-source-inventory.json").read_bytes()
    amend_runtime(builder, root, out, protocol)
    assert builder.prepare(root) == protocol
    assert (out / "review-protocol.json").read_bytes() == frozen_protocol
    assert (out / "runtime-source-inventory.json").read_bytes() == original_inventory
    assert all((out / name).read_bytes() == raw for name, raw in requests.items())


@pytest.mark.parametrize(
    "failure", ["missing", "bad_hash", "unapproved", "out_of_scope", "changed_requests"]
)
def test_invalid_capture_amendment_cannot_resume_frozen_reviews(repository, failure):
    builder, root, out, protocol = freeze(repository)
    amendment = amend_runtime(builder, root, out, protocol)
    if failure == "missing":
        (out / "review-capture-amendment.json").unlink()
    else:
        if failure == "bad_hash":
            amendment["amended_runtime_inventory"]["sha256"] = "f" * 64
        elif failure == "unapproved":
            amendment["reason"] = "rewrite reviewer decisions"
        elif failure == "out_of_scope":
            amendment["changed_sources"][0]["path"] = "src/demo.py"
        else:
            amendment["unchanged_bindings"]["requests"][0]["request"]["sha256"] = (
                "f" * 64
            )
        save(out, "review-capture-amendment.json", amendment)
    with pytest.raises(ValueError, match="runtime|amendment|checksum"):
        builder.prepare(root)


def test_adjudicator_retains_legacy_or_both_prior_citations_but_rejects_partial_extras(
    repository,
):
    builder, root, out, protocol = freeze(repository)
    case = builder.AICaseSpec.model_validate_json(
        builder.read_pin(out, protocol.case_inputs[0])
    )
    caps = []
    for role in builder.ROLES[:2]:
        name = f"requests/{case.case_id}/{role}"
        request = builder.AIReviewRequest.model_validate_json(
            (out / name / "request.json").read_bytes()
        )
        caps.append(
            capture(
                builder,
                out,
                request,
                name,
                "2026-10-06T01:00:00Z",
                "2026-10-06T02:00:00Z",
            )[0]
        )
    request = builder.adjudicator(
        case.case_id, root=root, captures=caps, materialized_at="2026-10-06T03:00:00Z"
    )
    name = f"requests/{case.case_id}/ai_adjudicator"
    cap_pin, event_pin, final_pin, _, _ = capture(
        builder, out, request, name, "2026-10-06T03:00:00Z", "2026-10-06T04:00:00Z"
    )
    original = json.loads(builder.read_pin(out, final_pin))
    cap = json.loads(builder.read_pin(out, cap_pin))
    events = json.loads(builder.read_pin(out, event_pin))
    priors = [pin.model_dump() for pin in request.prior_responses]
    unrelated = save(out, "unrelated-final.json", {"unrelated": True})
    for extra, valid in (
        ([], True),
        (priors, True),
        (priors[:1], False),
        (priors + priors[:1], False),
        ([unrelated], False),
    ):
        final = dict(original)
        final["evidence"] = original["evidence"] + extra
        updated_final = save(out, final_pin["path"], final)
        events["final_sha256"] = updated_final["sha256"]
        cap["host_events"] = save(out, event_pin["path"], events)
        cap["exact_final"] = updated_final
        updated_cap = save(out, cap_pin["path"], cap)
        if valid:
            builder.validate_capture(out, updated_cap)
        else:
            with pytest.raises(ValueError, match="exact visible evidence"):
                builder.validate_capture(out, updated_cap)
