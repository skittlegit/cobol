"""Gate tests for the additive stage-aware review contract."""

import pytest
from pydantic import ValidationError

from scripts.stage_review_contracts import (
    StageInheritedIssue,
    StageInheritedIssuePacket,
    StageReviewIssue,
    StageReviewResponse,
    validate_inherited_classifications,
)

PIN = {"path": "source.cbl", "sha256": "a" * 64}


def issue(category="post_patch_validation_obligation", index=0):
    return StageReviewIssue(
        category=category,
        text="Run the actual patch",
        rationale="Patch does not yet exist",
        evidence=[{"pin": PIN, "quote": "STOP RUN"}],
        inherited_issue_index=index,
    )


def response(**changes):
    payload = {
        "case_id": "migration_demo",
        "role": "ai_primary",
        "decision": "include",
        "rationale": "grounded",
        "scope_judgment": "finite",
        "intended_fixture_judgment": "actual",
        "regression_fixture_judgment": "actual",
        "capability_judgment": "actual",
        "duplicate_source_judgment": "dependent",
        "evidence": [PIN],
        "post_patch_validation_obligations": [issue()],
        "inherited_issue_classifications": [issue()],
    }
    payload.update(changes)
    return StageReviewResponse(**payload)


def packet():
    return StageInheritedIssuePacket(
        case_id="migration_demo",
        issues=[
            StageInheritedIssue(
                index=0, text="Run the actual patch", final_pin=PIN, final_issue_index=0
            )
        ],
        historical_finals=[PIN],
    )


def test_exhaustive_classification_and_retained_obligation():
    validate_inherited_classifications(response(), packet())


@pytest.mark.parametrize(
    "change",
    [
        {"inherited_issue_classifications": []},
        {"post_patch_validation_obligations": []},
    ],
)
def test_omitting_inherited_concern_or_category_rejects(change):
    with pytest.raises(ValueError):
        validate_inherited_classifications(response(**change), packet())


def test_v1_schema_and_model_identity_claims_rejected():
    with pytest.raises(ValidationError):
        response(schema_version="migration-ai-review-response-v1")
    with pytest.raises(ValidationError):
        response(model="claimed-provider")


def test_keyword_never_changes_explicit_blocker():
    blocker = issue("pre_generation_blocker")
    out = response(
        pre_generation_blockers=[blocker],
        post_patch_validation_obligations=[],
        inherited_issue_classifications=[blocker],
    )
    validate_inherited_classifications(out, packet())
    assert out.pre_generation_blockers


import json

from scripts.stage_review_contracts import (
    StageCanonicalCase,
    StageHostSessionEvents,
    StageReviewCapture,
    StageReviewEvidence,
    StageReviewProtocol,
    StageReviewRequest,
    load_stage_canonical_roster,
    model_sha256,
    response_schema_sha256,
)
from tests.test_migration_ai_review import make_graph, pin


def stage_graph(tmp_path, blocker=False):
    root, roster, _, spec, oldprotocol, oldrequests, oldevents = make_graph(tmp_path)
    packet_pin = pin(
        root,
        "inherited.json",
        StageInheritedIssuePacket(
            case_id=spec.case_id,
            issues=[],
            historical_finals=[
                pin(
                    root,
                    f"finals/{role}.json",
                    json.loads((root / f"finals/{role}.json").read_text()),
                )
                for role in ("ai_primary", "independent_ai_verifier", "ai_adjudicator")
            ],
        ).model_dump(mode="json"),
    )
    protocol_data = oldprotocol.model_dump(mode="json")
    protocol_data.update(
        schema_version="migration-stage-review-protocol-v1",
        inherited_issue_packets=[packet_pin.model_dump()],
        response_schema_sha256=response_schema_sha256(),
    )
    protocol = StageReviewProtocol(**protocol_data)
    protocol_pin = pin(root, "stage-protocol.json", protocol.model_dump(mode="json"))
    finals = []
    captures = []
    obligations = []
    for req, event in zip(oldrequests, oldevents, strict=True):
        old = json.loads((root / f"finals/{req.reviewer.role}.json").read_text())
        old.update(
            schema_version="migration-stage-review-response-v1",
            inherited_issue_classifications=[],
        )
        concern = StageReviewIssue(
            category="pre_generation_blocker"
            if blocker
            else "post_patch_validation_obligation",
            text="Actual patch validation remains mandatory",
            rationale="Inspect exact source before generation and execute generated patch afterward",
            evidence=[{"pin": spec.source_evidence[0], "quote": "STOP RUN"}],
        )
        old[
            "pre_generation_blockers"
            if blocker
            else "post_patch_validation_obligations"
        ] = [concern.model_dump(mode="json")]
        response = StageReviewResponse(**old)
        final = pin(
            root,
            f"stage-finals/{req.reviewer.role}.json",
            response.model_dump(mode="json"),
        )
        request_data = req.model_dump(mode="json")
        request_data.update(
            schema_version="migration-stage-review-request-v1",
            protocol=protocol_pin.model_dump(),
            inherited_issues=packet_pin.model_dump(),
            response_schema_sha256=response_schema_sha256(),
            prior_responses=[p.model_dump() for p in finals]
            if req.reviewer.role == "ai_adjudicator"
            else [],
        )
        request = StageReviewRequest(**request_data)
        request_pin = pin(
            root,
            f"stage-requests/{req.reviewer.role}.json",
            request.model_dump(mode="json"),
        )
        event_data = event.model_dump(mode="json")
        event_data.update(
            task_id="stage-" + event.task_id,
            session_id="stage-" + event.session_id,
            schema_version="migration-stage-host-session-events-v1",
            request_sha256=model_sha256(request),
            final_sha256=final.sha256,
        )
        events = StageHostSessionEvents(**event_data)
        events_pin = pin(
            root,
            f"stage-events/{req.reviewer.role}.json",
            events.model_dump(mode="json"),
        )
        capture = StageReviewCapture(
            request=request_pin,
            request_sha256=model_sha256(request),
            exact_final=final,
            host_events=events_pin,
        )
        captures.append(
            pin(
                root,
                f"stage-captures/{req.reviewer.role}.json",
                capture.model_dump(mode="json"),
            )
        )
        finals.append(final)
        if concern not in obligations and not blocker:
            obligations.append(concern)
    evidence = StageReviewEvidence(
        case_id=spec.case_id,
        case_input=protocol.case_inputs[0],
        protocol=protocol_pin,
        inherited_issues=packet_pin,
        captures=captures,
    )
    evidence_pin = pin(root, "stage-evidence.json", evidence.model_dump(mode="json"))
    data = spec.model_dump(mode="json")
    data.pop("schema_version")
    case = StageCanonicalCase(
        **data,
        review_protocol_sha256=protocol_pin.sha256,
        review_evidence_sha256=evidence_pin.sha256,
        review_evidence=evidence_pin,
        post_patch_validation_obligations=obligations,
    )
    roster.write_text(case.model_dump_json() + "\n")
    return root, roster, case


def stage_load(graph):
    root, roster, _ = graph
    return load_stage_canonical_roster(
        roster, review_evidence_root=root, protocol_path=root / "stage-protocol.json"
    )


def test_stage_chain_retains_obligations_and_pending_state(tmp_path):
    graph = stage_graph(tmp_path)
    assert stage_load(graph) == (graph[2],)
    assert graph[2].post_patch_validation_obligations
    assert (
        graph[2].review_state == "stage_reviewed_generation_eligible_validation_pending"
    )
    assert "eligible_for_evaluation" not in graph[2].model_dump()


def test_include_with_any_blocker_cannot_promote(tmp_path):
    with pytest.raises(ValueError, match="does not approve"):
        stage_load(stage_graph(tmp_path, blocker=True))


def test_canonical_cannot_drop_validation_obligation(tmp_path):
    graph = stage_graph(tmp_path)
    payload = graph[2].model_dump(mode="json")
    payload["post_patch_validation_obligations"] = []
    graph[1].write_text(json.dumps(payload) + "\n")
    with pytest.raises(ValueError, match="dropped"):
        stage_load(graph)


def test_fixture_tampering_fails_before_acceptance(tmp_path):
    graph = stage_graph(tmp_path)
    (graph[0] / "fixtures/demo.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        stage_load(graph)


def test_reuse_of_historical_context_rejects(tmp_path):
    graph = stage_graph(tmp_path)
    payload = json.loads((graph[0] / "events/ai_primary.json").read_bytes())
    payload["task_id"] = "stage-task-ai_primary"
    pin(graph[0], "unrelated/historical-events.json", payload)
    with pytest.raises(ValueError, match="reused"):
        stage_load(graph)


def test_inherited_packet_cannot_omit_a_historical_issue(tmp_path):
    from cobol_archaeologist.migration.ai_review import AIReviewResponse
    from scripts.stage_review_contracts import validate_issue_packet

    out = response().model_dump(mode="json")
    for key in (
        "pre_generation_blockers",
        "scope_limitations",
        "post_patch_validation_obligations",
        "historical_evidence_qualifications",
        "inherited_issue_classifications",
        "classification_disagreements_resolved",
    ):
        out.pop(key)
    out["schema_version"] = "migration-ai-review-response-v1"
    out["unresolved_issues"] = ["Exact retained concern"]
    old = AIReviewResponse(**out)
    oldpin = pin(tmp_path, "old-final.json", old.model_dump(mode="json"))
    packet = StageInheritedIssuePacket(
        case_id=old.case_id, issues=[], historical_finals=[oldpin]
    )
    with pytest.raises(ValueError, match="exhaust"):
        validate_issue_packet(packet, tmp_path)


def test_complete_grounded_exclusions_may_have_empty_accepted_roster(tmp_path):
    from scripts.stage_review_contracts import StageReviewDispositionManifest

    graph = stage_graph(tmp_path, blocker=True)
    root, roster, case = graph
    protocol_pin = pin(
        root,
        "stage-protocol.json",
        json.loads((root / "stage-protocol.json").read_bytes()),
    )
    disposition = StageReviewDispositionManifest(
        protocol=protocol_pin,
        cases=[{"case_id": case.case_id, "review_evidence": case.review_evidence}],
        accepted_case_ids=[],
        excluded_case_ids=[case.case_id],
        status="NOT_EVALUABLE",
    )
    disposition_pin = pin(
        root, "stage-disposition.json", disposition.model_dump(mode="json")
    )
    roster.write_text("")
    assert (
        load_stage_canonical_roster(
            roster,
            review_evidence_root=root,
            protocol_path=root / "stage-protocol.json",
            disposition_path=root / disposition_pin.path,
        )
        == ()
    )


def test_classification_evidence_quote_must_exist_in_exact_source(tmp_path):
    from scripts.stage_review_contracts import validate_stage_response

    graph = stage_graph(tmp_path)
    root, _, _ = graph
    request = StageReviewRequest.model_validate_json(
        (root / "stage-requests/ai_primary.json").read_bytes()
    )
    from cobol_archaeologist.migration.ai_review import AICaseSpec

    spec = AICaseSpec.model_validate_json((root / "inputs/demo.json").read_bytes())
    packet = StageInheritedIssuePacket.model_validate_json(
        (root / "inherited.json").read_bytes()
    )
    payload = json.loads((root / "stage-finals/ai_primary.json").read_bytes())
    payload["post_patch_validation_obligations"][0]["evidence"][0]["quote"] = (
        "invented execution evidence"
    )
    with pytest.raises(ValueError, match="quote absent"):
        validate_stage_response(
            StageReviewResponse(**payload), spec, request, packet, root
        )


def test_primary_cannot_bind_any_other_stage_final(tmp_path):
    graph = stage_graph(tmp_path)
    payload = json.loads((graph[0] / "stage-requests/ai_primary.json").read_bytes())
    payload["prior_responses"] = [PIN]
    with pytest.raises(ValueError, match="blind"):
        StageReviewRequest(**payload)


def test_canonical_cannot_remove_mandatory_checks(tmp_path):
    graph = stage_graph(tmp_path)
    payload = graph[2].model_dump(mode="json")
    payload["mandatory_validation_obligations"] = []
    with pytest.raises(ValueError, match="mandatory"):
        StageCanonicalCase(**payload)
