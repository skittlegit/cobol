"""AI review promotion must preserve provenance and exact case evidence."""

from __future__ import annotations

import hashlib
import json

import pytest

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICanonicalMigrationCase,
    AICaseSpec,
    AIHostSessionEvents,
    AIReviewCapture,
    AIReviewerIdentity,
    AIReviewEvidence,
    AIReviewProtocol,
    AIReviewRequest,
    AIReviewResponse,
    load_ai_canonical_roster,
    model_sha256,
    response_schema_sha256,
)
from cobol_archaeologist.migration.contracts import MigrationEvidencePin


def pin(root, name, value):
    raw = (
        value
        if isinstance(value, bytes)
        else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    )
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return MigrationEvidencePin(path=name, sha256=hashlib.sha256(raw).hexdigest())


def make_graph(tmp_path, decisions=None):
    root = tmp_path
    source = pin(root, "sources/DEMO.cbl", b"PROCEDURE DIVISION. STOP RUN.")
    regulation = pin(root, "regulation.json", {"clause": "source-grounded clause"})
    fixture = pin(root, "fixtures/demo.json", {"inputs": [1], "expected": [2]})
    authorization = pin(
        root,
        "authorization.txt",
        b"AI primary plus independent AI verification and adjudication authorized",
    )
    manifest = pin(root, "candidate-manifest.json", {"case_ids": ["migration_demo"]})
    spec = AICaseSpec(
        case_id="migration_demo",
        instance_id="drift_000001",
        drift_type="D1_stale_threshold",
        stratum="local",
        validation_capability="batch_executable",
        primary_program="DEMO",
        frozen_sources=[{"path": "DEMO.cbl", "sha256": source.sha256}],
        source_evidence=[source],
        regulation_evidence=regulation,
        fixture_evidence=[fixture],
        allowed_source_scope=[{"path": "DEMO.cbl", "line_spans": [[1, 1]]}],
        intended_behavior={"check_id": "intended", "description": "intended"},
        unaffected_regressions=[{"check_id": "unchanged", "description": "unchanged"}],
        detector_input_ref="detector.json",
        oracle_evidence_ref="oracle.json",
        validation_protocol_sha256="a" * 64,
        source_bundle_group="demo",
        duplicate_source_justification="only case",
    )
    input_pin = pin(root, "inputs/demo.json", spec.model_dump(mode="json"))
    reviewers = [
        AIReviewerIdentity(role=role, model="gpt-6.1-sol", reasoning="max")
        for role in ROLES
    ]
    protocol = AIReviewProtocol(
        frozen_at="2026-10-06T00:00:00Z",
        authorization_evidence=authorization,
        candidate_manifest=manifest,
        runtime_source_sha256="b" * 64,
        response_schema_sha256=response_schema_sha256(),
        case_inputs=[input_pin],
        reviewers=reviewers,
    )
    protocol_pin = pin(root, "review-protocol.json", protocol.model_dump(mode="json"))
    finals, captures, requests, events = [], [], [], []
    for index, reviewer in enumerate(reviewers):
        role = reviewer.role
        response = AIReviewResponse(
            case_id=spec.case_id,
            role=role,
            decision=(decisions or {}).get(role, "include"),
            rationale="checked source",
            scope_judgment="bounded",
            intended_fixture_judgment="concrete",
            regression_fixture_judgment="concrete",
            capability_judgment="available",
            duplicate_source_judgment="unique",
            evidence=[source, regulation, fixture],
        )
        final = pin(root, f"finals/{role}.json", response.model_dump(mode="json"))
        prompt = pin(root, f"prompts/{role}.txt", b"case-local source fixture review")
        request = AIReviewRequest(
            case_id=spec.case_id,
            reviewer=reviewer,
            protocol=protocol_pin,
            case_input=input_pin,
            prompt=prompt,
            response_schema_sha256=response_schema_sha256(),
            prior_responses=finals[:2] if index == 2 else [],
        )
        request_pin = pin(
            root, f"requests/{role}.json", request.model_dump(mode="json")
        )
        transcript = pin(
            root, f"transcripts/{role}.txt", b"captured session transcript"
        )
        hour = 3 if index == 2 else 1
        event = AIHostSessionEvents(
            provenance="host_captured_collaboration_session",
            task_id=f"task-{role}",
            session_id=f"session-{role}",
            reviewer=reviewer,
            request_sha256=model_sha256(request),
            final_sha256=final.sha256,
            started_at=f"2026-10-06T0{hour}:00:00Z",
            completed_at=f"2026-10-06T0{hour + 1}:00:00Z",
            raw_transcript=transcript,
        )
        event_pin = pin(root, f"events/{role}.json", event.model_dump(mode="json"))
        capture = AIReviewCapture(
            request=request_pin,
            request_sha256=model_sha256(request),
            exact_final=final,
            host_events=event_pin,
        )
        captures.append(
            pin(root, f"captures/{role}.json", capture.model_dump(mode="json"))
        )
        finals.append(final)
        requests.append(request)
        events.append(event)
    evidence = AIReviewEvidence(
        case_id=spec.case_id,
        case_input=input_pin,
        protocol=protocol_pin,
        captures=captures,
    )
    evidence_pin = pin(root, "reviews/demo.json", evidence.model_dump(mode="json"))
    kwargs = spec.model_dump(mode="json")
    kwargs.pop("schema_version")
    case = AICanonicalMigrationCase(
        **kwargs,
        review_protocol_sha256=protocol_pin.sha256,
        review_evidence_sha256=evidence_pin.sha256,
        review_evidence=evidence_pin,
    )
    roster = root / "cases.jsonl"
    roster.write_text(case.model_dump_json() + "\n", encoding="utf-8")
    return root, roster, case, spec, protocol, requests, events


@pytest.fixture
def graph(tmp_path):
    return make_graph(tmp_path)


def load(graph):
    root, roster, *_ = graph
    return load_ai_canonical_roster(
        roster, review_evidence_root=root, protocol_path=root / "review-protocol.json"
    )


def test_nonhuman_chain_promotes_without_human_state(graph):
    assert load(graph) == (graph[2],)
    assert graph[2].nonhuman
    assert graph[2].review_state == "ai_primary_reviewed_verified_and_adjudicated"


def test_changed_fixture_bytes_reject_even_unchanged_review(graph):
    (graph[0] / "fixtures/demo.json").write_bytes(b"changed expectations")
    with pytest.raises(ValueError, match="checksum"):
        load(graph)


def test_changed_canonical_scope_rejects_promotion(graph):
    raw = graph[2].model_dump(mode="json")
    raw["allowed_source_scope"][0]["line_spans"] = [[1, 2]]
    graph[1].write_text(json.dumps(raw) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed source, fixture, scope"):
        load(graph)


def test_primary_cannot_receive_verifier_result(graph):
    request = graph[5][0].model_dump(mode="json")
    request["prior_responses"] = [{"path": "final.json", "sha256": "a" * 64}]
    with pytest.raises(ValueError, match="blind"):
        AIReviewRequest.model_validate(request)


def test_human_attestation_fields_and_false_nonhuman_rejected(graph):
    raw = graph[2].model_dump(mode="json")
    raw["human_reviewer_verified"] = True
    with pytest.raises(ValueError):
        AICanonicalMigrationCase.model_validate(raw)
    raw.pop("human_reviewer_verified")
    raw["nonhuman"] = False
    with pytest.raises(ValueError):
        AICanonicalMigrationCase.model_validate(raw)


def test_duplicate_case_rows_rejected(graph):
    graph[1].write_text(graph[1].read_text(encoding="utf-8") * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load(graph)


def test_path_escape_rejected():
    with pytest.raises(ValueError):
        MigrationEvidencePin(path="../fixture.json", sha256="a" * 64)


def test_duplicate_role_protocol_rejected(graph):
    raw = graph[4].model_dump(mode="json")
    raw["reviewers"][2] = raw["reviewers"][0]
    with pytest.raises(ValueError, match="three distinct"):
        AIReviewProtocol.model_validate(raw)


def test_schema_identity_is_deterministic_and_nonhuman():
    assert response_schema_sha256() == response_schema_sha256()
    assert "human_primary" not in json.dumps(AIReviewResponse.model_json_schema())


def repin_event(graph, role, change):
    root, roster, case, *_ = graph
    event_path = f"events/{role}.json"
    event = json.loads((root / event_path).read_text(encoding="utf-8"))
    event.update(change)
    event_pin = pin(root, event_path, event)
    capture_path = f"captures/{role}.json"
    capture = json.loads((root / capture_path).read_text(encoding="utf-8"))
    capture["host_events"] = event_pin.model_dump()
    capture_pin = pin(root, capture_path, capture)
    evidence = json.loads((root / "reviews/demo.json").read_text(encoding="utf-8"))
    index = ROLES.index(role)
    evidence["captures"][index] = capture_pin.model_dump()
    evidence_pin = pin(root, "reviews/demo.json", evidence)
    raw = case.model_dump(mode="json")
    raw["review_evidence"] = evidence_pin.model_dump()
    raw["review_evidence_sha256"] = evidence_pin.sha256
    roster.write_text(json.dumps(raw) + "\n", encoding="utf-8")


@pytest.mark.parametrize("field", ["task_id", "session_id"])
def test_reused_context_identity_rejected_even_after_outer_repins(graph, field):
    repin_event(graph, ROLES[1], {field: getattr(graph[6][0], field)})
    with pytest.raises(ValueError, match="reused review task or session"):
        load(graph)


def test_adjudication_must_follow_sealed_independent_results(graph):
    repin_event(graph, ROLES[2], {"started_at": "2026-10-06T01:30:00Z"})
    with pytest.raises(ValueError, match="adjudication precedes"):
        load(graph)


def test_changed_final_rejected(graph):
    (graph[0] / f"finals/{ROLES[0]}.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="checksum"):
        load(graph)


@pytest.mark.parametrize("defect", [None, "partial", "extra", "hash", "duplicate"])
def test_loader_adjudication_evidence_can_add_only_both_bound_prior_pins(graph, defect):
    root = graph[0]
    role = "ai_adjudicator"
    response = json.loads((root / f"finals/{role}.json").read_bytes())
    request = graph[5][2]
    response["evidence"].extend(p.model_dump(mode="json") for p in request.prior_responses)
    if defect == "partial":
        response["evidence"].pop()
    elif defect == "extra":
        response["evidence"].append({"path": "unbound.json", "sha256": "f" * 64})
    elif defect == "hash":
        response["evidence"][-1]["sha256"] = "f" * 64
    elif defect == "duplicate":
        response["evidence"].append(response["evidence"][-1].copy())
    final_pin = pin(root, f"finals/{role}.json", response)
    capture = json.loads((root / f"captures/{role}.json").read_bytes())
    capture["exact_final"] = final_pin.model_dump(mode="json")
    pin(root, f"captures/{role}.json", capture)
    repin_event(graph, role, {"final_sha256": final_pin.sha256})
    if defect:
        with pytest.raises(ValueError, match="unbound citations"):
            load(graph)
    else:
        assert load(graph)[0].case_id == graph[2].case_id


def test_model_authored_extra_capture_identity_is_rejected(graph):
    raw = graph[6][0].model_dump(mode="json")
    raw["human_reviewer_verified"] = True
    with pytest.raises(ValueError):
        AIHostSessionEvents.model_validate(raw)


def disposition(graph, accepted):
    from cobol_archaeologist.migration.ai_review import AIReviewDispositionManifest

    root, _, case, *_ = graph
    manifest = AIReviewDispositionManifest(
        protocol=MigrationEvidencePin(
            path="review-protocol.json", sha256=case.review_protocol_sha256
        ),
        cases=[{"case_id": case.case_id, "review_evidence": case.review_evidence}],
        accepted_case_ids=[case.case_id] if accepted else [],
        excluded_case_ids=[] if accepted else [case.case_id],
        status="COMPLETE_ALL_ACCEPTED" if accepted else "NOT_EVALUABLE",
    )
    path = root / "disposition.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    return path


def load_disposition(graph, path):
    root, roster, *_ = graph
    return load_ai_canonical_roster(
        roster,
        review_evidence_root=root,
        protocol_path=root / "review-protocol.json",
        disposition_path=path,
    )


def test_accepted_disposition_preserves_approved_case(graph):
    assert load_disposition(graph, disposition(graph, True)) == (graph[2],)


@pytest.mark.parametrize("decision", ["exclude", "needs_revision"])
def test_grounded_exclusion_accounts_case_without_fake_eligibility(tmp_path, decision):
    graph = make_graph(tmp_path, {ROLES[1]: decision})
    path = disposition(graph, False)
    graph[1].write_text("", encoding="utf-8")
    assert load_disposition(graph, path) == ()
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "NOT_EVALUABLE"


def test_adjudicator_include_does_not_erase_verifier_exclusion(tmp_path):
    graph = make_graph(tmp_path, {ROLES[1]: "exclude"})
    with pytest.raises(ValueError, match="contradicts sealed"):
        load_disposition(graph, disposition(graph, True))


def test_all_approved_case_cannot_be_silently_excluded(graph):
    graph[1].write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="contradicts sealed"):
        load_disposition(graph, disposition(graph, False))


def test_disposition_missing_protocol_case_rejected(graph):
    path = disposition(graph, True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["cases"][0]["case_id"] = "migration_other"
    raw["accepted_case_ids"] = ["migration_other"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="omits or reorders"):
        load_disposition(graph, path)


def test_excluded_case_raw_final_tamper_still_rejected(tmp_path):
    graph = make_graph(tmp_path, {ROLES[0]: "exclude"})
    path = disposition(graph, False)
    graph[1].write_text("", encoding="utf-8")
    (graph[0] / f"finals/{ROLES[0]}.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="checksum"):
        load_disposition(graph, path)
