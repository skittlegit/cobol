"""Additive stage review; generation eligibility never proves patch validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICaseSpec,
    AIHostSessionEvents,
    AIReviewCapture,
    AIReviewEvidence,
    AIReviewProtocol,
    AIReviewRequest,
    AIReviewResponse,
    Digest,
    StrictModel,
    _pinned,
    model_sha256,
)
from cobol_archaeologist.migration.contracts import MigrationEvidencePin

Category = Literal[
    "pre_generation_blocker",
    "scope_limitation",
    "post_patch_validation_obligation",
    "historical_evidence_qualification",
]
CATEGORIES = (
    "pre_generation_blocker",
    "scope_limitation",
    "post_patch_validation_obligation",
    "historical_evidence_qualification",
)
CATEGORY_FIELDS = (
    "pre_generation_blockers",
    "scope_limitations",
    "post_patch_validation_obligations",
    "historical_evidence_qualifications",
)
ACCEPTANCE_POLICY = "all_three_include_zero_pre_generation_blockers"
MANDATORY_VALIDATION = (
    "patch_scope",
    "clean_application",
    "parser_integrity",
    "call_graph_dataflow_slice_consistency",
    "compiler_execution",
    "intended_behavior",
    "unaffected_regression_behavior",
    "affected_host_fanout",
    "exact_source_binding",
)
REPORT_LIMITATIONS = (
    "finite_fixtures_do_not_prove_complete_equivalence_or_universal_compliance",
    "no_untested_host_fanout_claim",
    "dependent_source_cases_are_not_independent_contributions",
    "all_failed_patches_abstentions_unavailable_checks_and_infrastructure_failures_remain_visible",
)


class StageInheritedIssue(StrictModel):
    index: int = Field(ge=0)
    text: str = Field(min_length=1)
    final_pin: MigrationEvidencePin
    final_issue_index: int = Field(ge=0)


class StageInheritedIssuePacket(StrictModel):
    schema_version: Literal["migration-stage-review-inherited-issues-v1"] = (
        "migration-stage-review-inherited-issues-v1"
    )
    case_id: str
    issues: tuple[StageInheritedIssue, ...]
    historical_finals: tuple[MigrationEvidencePin, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def indices(self):
        if tuple(i.index for i in self.issues) != tuple(range(len(self.issues))):
            raise ValueError("inherited issue indices must be exhaustive and ordered")
        keys = [
            (i.final_pin.path, i.final_pin.sha256, i.final_issue_index)
            for i in self.issues
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate inherited issue origin")
        return self


class StageIssueEvidence(StrictModel):
    pin: MigrationEvidencePin
    quote: str = Field(min_length=1)


class StageReviewIssue(StrictModel):
    category: Category
    text: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: tuple[StageIssueEvidence, ...] = Field(min_length=1)
    inherited_issue_index: int | None = Field(default=None, ge=0)


class StageReviewProtocol(AIReviewProtocol):
    schema_version: Literal["migration-stage-review-protocol-v1"] = (
        "migration-stage-review-protocol-v1"
    )
    inherited_issue_packets: tuple[MigrationEvidencePin, ...] = Field(min_length=1)
    acceptance_policy: Literal["all_three_include_zero_pre_generation_blockers"] = (
        ACCEPTANCE_POLICY
    )

    @model_validator(mode="after")
    def packets(self):
        if len(self.inherited_issue_packets) != len(self.case_inputs) or len(
            {p.path for p in self.inherited_issue_packets}
        ) != len(self.inherited_issue_packets):
            raise ValueError("one unique inherited issue packet per case required")
        return self


class StageReviewRequest(AIReviewRequest):
    schema_version: Literal["migration-stage-review-request-v1"] = (
        "migration-stage-review-request-v1"
    )
    inherited_issues: MigrationEvidencePin


class StageReviewResponse(AIReviewResponse):
    schema_version: Literal["migration-stage-review-response-v1"] = (
        "migration-stage-review-response-v1"
    )
    pre_generation_blockers: tuple[StageReviewIssue, ...] = ()
    scope_limitations: tuple[StageReviewIssue, ...] = ()
    post_patch_validation_obligations: tuple[StageReviewIssue, ...] = ()
    historical_evidence_qualifications: tuple[StageReviewIssue, ...] = ()
    inherited_issue_classifications: tuple[StageReviewIssue, ...]
    classification_disagreements_resolved: tuple[int, ...] = ()

    @model_validator(mode="after")
    def typed_issues(self):
        if self.unresolved_issues:
            raise ValueError(
                "fresh concerns must be stage-typed; ambiguous concerns are blockers"
            )
        for category, field in zip(CATEGORIES, CATEGORY_FIELDS, strict=True):
            if any(issue.category != category for issue in getattr(self, field)):
                raise ValueError("issue category differs from containing category")
        if self.role != "ai_adjudicator" and self.classification_disagreements_resolved:
            raise ValueError(
                "only fresh adjudicator resolves classification disagreements"
            )
        if len(set(self.classification_disagreements_resolved)) != len(
            self.classification_disagreements_resolved
        ):
            raise ValueError("duplicate disagreement resolution")
        return self


class StageReviewCapture(AIReviewCapture):
    schema_version: Literal["migration-stage-review-capture-v1"] = (
        "migration-stage-review-capture-v1"
    )


class StageHostSessionEvents(AIHostSessionEvents):
    schema_version: Literal["migration-stage-host-session-events-v1"] = (
        "migration-stage-host-session-events-v1"
    )


class StageReviewEvidence(AIReviewEvidence):
    schema_version: Literal["migration-stage-review-evidence-v1"] = (
        "migration-stage-review-evidence-v1"
    )
    inherited_issues: MigrationEvidencePin


class StageCanonicalCase(AICaseSpec):
    schema_version: Literal["migration-stage-reviewed-case-v1"] = (
        "migration-stage-reviewed-case-v1"
    )
    review_protocol_sha256: Digest
    review_evidence_sha256: Digest
    review_evidence: MigrationEvidencePin
    review_state: Literal["stage_reviewed_generation_eligible_validation_pending"] = (
        "stage_reviewed_generation_eligible_validation_pending"
    )
    acceptance_policy: Literal["all_three_include_zero_pre_generation_blockers"] = (
        ACCEPTANCE_POLICY
    )
    mandatory_validation_obligations: tuple[str, ...] = MANDATORY_VALIDATION
    reporting_limitations: tuple[str, ...] = REPORT_LIMITATIONS
    scope_limitations: tuple[StageReviewIssue, ...] = ()
    post_patch_validation_obligations: tuple[StageReviewIssue, ...] = ()
    historical_evidence_qualifications: tuple[StageReviewIssue, ...] = ()
    eligible_for_generation: Literal[True] = True
    nonhuman: Literal[True] = True

    @model_validator(mode="after")
    def mandatory(self):
        if (
            self.mandatory_validation_obligations != MANDATORY_VALIDATION
            or self.reporting_limitations != REPORT_LIMITATIONS
        ):
            raise ValueError(
                "mandatory validation and reporting limits must be retained"
            )
        return self


def response_schema_sha256() -> str:
    return hashlib.sha256(
        json.dumps(
            StageReviewResponse.model_json_schema(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def validate_response_evidence(response, required, request):
    expected = {(p.path, p.sha256) for p in required}
    actual = [(p.path, p.sha256) for p in response.evidence]
    allowed = [expected]
    if request.reviewer.role == "ai_adjudicator":
        allowed.append(expected | {(p.path, p.sha256) for p in request.prior_responses})
    if len(actual) != len(set(actual)) or set(actual) not in allowed:
        raise ValueError(
            "response lacks exact case source/fixture evidence or has unbound citations"
        )


def validate_inherited_classifications(response, packet):
    if response.case_id != packet.case_id:
        raise ValueError("inherited issue case identity differs")
    classifications = response.inherited_issue_classifications
    if tuple(i.inherited_issue_index for i in classifications) != tuple(
        range(len(packet.issues))
    ):
        raise ValueError(
            "inherited classifications must account for every exact issue index"
        )
    for inherited, classified in zip(packet.issues, classifications, strict=True):
        if inherited.text != classified.text:
            raise ValueError("inherited issue text changed")
    typed = [i for field in CATEGORY_FIELDS for i in getattr(response, field)]
    referred = [i for i in typed if i.inherited_issue_index is not None]
    if len(referred) != len(classifications) or {
        i.inherited_issue_index for i in referred
    } != set(range(len(packet.issues))):
        raise ValueError(
            "every inherited classification must be retained in its category"
        )
    by_index = {i.inherited_issue_index: i for i in referred}
    if any(by_index[i.inherited_issue_index] != i for i in classifications):
        raise ValueError("category issue differs from inherited classification")


def validate_issue_packet(packet, root):
    """Check exact historical text and index, without using historical judgments."""
    expected = []
    if len({p.path for p in packet.historical_finals}) != len(packet.historical_finals):
        raise ValueError("duplicate inherited historical finals")
    for final_pin in packet.historical_finals:
        final = AIReviewResponse.model_validate_json(_pinned(root, final_pin))
        if final.case_id != packet.case_id:
            raise ValueError("historical final case differs")
        expected.extend(
            (final_pin, index, text)
            for index, text in enumerate(final.unresolved_issues)
        )
    actual = [
        (issue.final_pin, issue.final_issue_index, issue.text)
        for issue in packet.issues
    ]
    if actual != expected:
        raise ValueError(
            "inherited packet must exhaust every exact historical final/text/index"
        )


def validate_stage_response(response, spec, request, packet, root):
    required = (*spec.source_evidence, spec.regulation_evidence, *spec.fixture_evidence)
    validate_response_evidence(response, required, request)
    validate_inherited_classifications(response, packet)
    if response.case_id != spec.case_id or response.role != request.reviewer.role:
        raise ValueError("response case or role differs")
    allowed = {(p.path, p.sha256) for p in required}
    # DECISION: historical pins identify concerns only; classifications must be
    # grounded in actual case evidence, optionally both newly bound prior finals.
    if request.reviewer.role == "ai_adjudicator":
        allowed.update((p.path, p.sha256) for p in request.prior_responses)
    for field in CATEGORY_FIELDS:
        for issue in getattr(response, field):
            cited = []
            for evidence in issue.evidence:
                if (evidence.pin.path, evidence.pin.sha256) not in allowed:
                    raise ValueError("classification cites unbound evidence")
                if evidence.quote not in _pinned(root, evidence.pin).decode("utf-8"):
                    raise ValueError("classification quote absent from exact evidence")
                cited.append((evidence.pin.path, evidence.quote))
            if len(cited) != len(set(cited)):
                raise ValueError("duplicate classification evidence")


def _load_stage_review_chain(
    roster_path: Path,
    *,
    review_evidence_root: Path,
    protocol_path: Path,
    reviewed_bindings: tuple | None = None,
    require_inclusion: bool = True,
) -> tuple[StageCanonicalCase, ...]:
    root = review_evidence_root.resolve()
    protocol_raw = protocol_path.read_bytes()
    protocol_hash = hashlib.sha256(protocol_raw).hexdigest()
    protocol = StageReviewProtocol.model_validate_json(protocol_raw)
    if protocol.response_schema_sha256 != response_schema_sha256():
        raise ValueError("review response schema identity differs")
    _pinned(root, protocol.authorization_evidence)
    _pinned(root, protocol.candidate_manifest)
    inputs = {
        pin.path: AICaseSpec.model_validate_json(_pinned(root, pin))
        for pin in protocol.case_inputs
    }
    if len({spec.case_id for spec in inputs.values()}) != len(inputs):
        raise ValueError("duplicate protocol case IDs")
    cases = (
        reviewed_bindings
        if reviewed_bindings is not None
        else tuple(
            StageCanonicalCase.model_validate_json(line)
            for line in roster_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    )
    if (
        not cases
        or len({c.case_id for c in cases}) != len(cases)
        or len({c.instance_id for c in cases}) != len(cases)
    ):
        raise ValueError("canonical roster must have unique nonempty cases")
    if tuple(c.case_id for c in cases) != tuple(
        spec.case_id for spec in inputs.values()
    ):
        raise ValueError("roster differs from exact protocol case order")
    packets = tuple(
        StageInheritedIssuePacket.model_validate_json(_pinned(root, pin))
        for pin in protocol.inherited_issue_packets
    )
    if tuple(p.case_id for p in packets) != tuple(
        spec.case_id for spec in inputs.values()
    ):
        raise ValueError("inherited packets differ from exact protocol case order")
    for packet in packets:
        validate_issue_packet(packet, root)
    packet_by_id = {
        p.case_id: (p, pin)
        for p, pin in zip(packets, protocol.inherited_issue_packets, strict=True)
    }
    used_sessions, used_tasks = set(), set()
    historical_sessions, historical_tasks = set(), set()
    stage_sessions, stage_tasks = {}, {}
    # Reusing any retained v1 context cannot create a fresh stage review.
    for path in root.rglob("*.json"):
        try:
            payload = json.loads(path.read_bytes())
        except (ValueError, UnicodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") == "migration-ai-host-session-events-v1"
        ):
            historical = AIHostSessionEvents.model_validate(payload)
            historical_sessions.add(historical.session_id)
            historical_tasks.add(historical.task_id)
        if (
            isinstance(payload, dict)
            and payload.get("schema_version")
            == "migration-stage-host-session-events-v1"
        ):
            retained = StageHostSessionEvents.model_validate(payload)
            relative = path.relative_to(root).as_posix()
            stage_sessions.setdefault(retained.session_id, set()).add(relative)
            stage_tasks.setdefault(retained.task_id, set()).add(relative)
    for case in cases:
        if (
            case.review_protocol_sha256 != protocol_hash
            or case.review_evidence_sha256 != case.review_evidence.sha256
        ):
            raise ValueError("canonical case review pins differ")
        evidence = StageReviewEvidence.model_validate_json(
            _pinned(root, case.review_evidence)
        )
        if (
            evidence.case_id != case.case_id
            or evidence.case_input not in protocol.case_inputs
        ):
            raise ValueError("case-specific input evidence differs")
        spec = inputs[evidence.case_input.path]
        fields = set(AICaseSpec.model_fields) - {"schema_version"}
        if any(getattr(case, name) != getattr(spec, name) for name in fields):
            raise ValueError(
                "promoted case changed source, fixture, scope, or behavior"
            )
        if (
            evidence.protocol.sha256 != protocol_hash
            or _pinned(root, evidence.protocol) != protocol_raw
        ):
            raise ValueError("case protocol binding differs")
        packet, packet_pin = packet_by_id[case.case_id]
        if evidence.inherited_issues != packet_pin:
            raise ValueError("case inherited issue packet binding differs")
        required = (
            *spec.source_evidence,
            spec.regulation_evidence,
            *spec.fixture_evidence,
        )
        for pin in required:
            _pinned(root, pin)
        responses, event_by_role = {}, {}
        for capture_pin in evidence.captures:
            capture = StageReviewCapture.model_validate_json(_pinned(root, capture_pin))
            request = StageReviewRequest.model_validate_json(
                _pinned(root, capture.request)
            )
            events = StageHostSessionEvents.model_validate_json(
                _pinned(root, capture.host_events)
            )
            final_raw = _pinned(root, capture.exact_final)
            response = StageReviewResponse.model_validate_json(final_raw)
            role = request.reviewer.role
            if role in responses:
                raise ValueError("duplicate review role")
            if (
                request.reviewer not in protocol.reviewers
                or events.reviewer != request.reviewer
            ):
                raise ValueError(
                    "reviewer model/reasoning differs from frozen identity"
                )
            if (
                request.protocol != evidence.protocol
                or request.case_input != evidence.case_input
                or request.case_id != case.case_id
                or request.inherited_issues != packet_pin
            ):
                raise ValueError("request case/protocol identity differs")
            if request.response_schema_sha256 != protocol.response_schema_sha256:
                raise ValueError("request schema identity differs")
            if (
                capture.request_sha256 != model_sha256(request)
                or events.request_sha256 != capture.request_sha256
            ):
                raise ValueError("capture request model hash differs")
            if events.final_sha256 != capture.exact_final.sha256:
                raise ValueError("capture final identity differs")
            if (
                events.session_id in used_sessions
                or events.task_id in used_tasks
                or events.session_id in historical_sessions
                or events.task_id in historical_tasks
                or stage_sessions.get(events.session_id, set())
                != {capture.host_events.path}
                or stage_tasks.get(events.task_id, set()) != {capture.host_events.path}
            ):
                raise ValueError("reused review task or session")
            used_sessions.add(events.session_id)
            used_tasks.add(events.task_id)
            if not protocol.frozen_at < events.started_at < events.completed_at:
                raise ValueError("review capture timing differs from freeze")
            _pinned(root, events.raw_transcript)
            _pinned(root, request.prompt)
            if response.case_id != case.case_id or response.role != role:
                raise ValueError("response case or role differs")
            validate_stage_response(response, spec, request, packet, root)
            if require_inclusion and (
                response.decision != "include" or response.pre_generation_blockers
            ):
                raise ValueError("review does not approve an eligible case")
            responses[role] = (response, capture.exact_final, request)
            event_by_role[role] = events
        if set(responses) != set(ROLES):
            raise ValueError("missing distinct review roles")
        adjudication = responses["ai_adjudicator"][2]
        expected_prior = (
            responses["ai_primary"][1],
            responses["independent_ai_verifier"][1],
        )
        if adjudication.prior_responses != expected_prior:
            raise ValueError("adjudicator did not bind both independent finals")
        if event_by_role["ai_adjudicator"].started_at <= max(
            event_by_role[r].completed_at for r in ROLES[:2]
        ):
            raise ValueError("adjudication precedes independent sealed responses")
        adjudicator = responses["ai_adjudicator"][0]
        primary = responses["ai_primary"][0]
        verifier = responses["independent_ai_verifier"][0]
        disagreements = tuple(
            i
            for i, (a, b) in enumerate(
                zip(
                    primary.inherited_issue_classifications,
                    verifier.inherited_issue_classifications,
                    strict=True,
                )
            )
            if a.category != b.category
        )
        if adjudicator.classification_disagreements_resolved != disagreements:
            raise ValueError(
                "adjudicator must resolve every inherited classification disagreement exactly"
            )
        # DECISION: retain the union across all three fresh roles; adjudication
        # cannot silently remove an obligation or disclosed limitation.
        for field in CATEGORY_FIELDS[1:]:
            retained = []
            for role in ROLES:
                for issue in getattr(responses[role][0], field):
                    if issue not in retained:
                        retained.append(issue)
            if require_inclusion and getattr(case, field) != tuple(retained):
                raise ValueError(
                    "canonical case dropped reviewed obligations or limitations"
                )
    return cases


class StageReviewDispositionEntry(StrictModel):
    case_id: str
    review_evidence: MigrationEvidencePin


class StageReviewDispositionManifest(StrictModel):
    """Exhaustive accounting grounded in preserved exact review finals."""

    schema_version: Literal["migration-stage-review-disposition-v1"] = (
        "migration-stage-review-disposition-v1"
    )
    protocol: MigrationEvidencePin
    cases: tuple[StageReviewDispositionEntry, ...] = Field(min_length=1)
    accepted_case_ids: tuple[str, ...]
    excluded_case_ids: tuple[str, ...]
    status: Literal[
        "COMPLETE_ALL_ACCEPTED", "COMPLETE_WITH_EXCLUSIONS", "NOT_EVALUABLE"
    ]
    acceptance_policy: Literal["all_three_include_zero_pre_generation_blockers"] = (
        "all_three_include_zero_pre_generation_blockers"
    )
    nonhuman: Literal[True] = True

    @model_validator(mode="after")
    def accounting(self):
        ordered = tuple(case.case_id for case in self.cases)
        if len(set(ordered)) != len(ordered):
            raise ValueError("duplicate disposition case IDs")
        accepted, excluded = set(self.accepted_case_ids), set(self.excluded_case_ids)
        if len(accepted) != len(self.accepted_case_ids) or len(excluded) != len(
            self.excluded_case_ids
        ):
            raise ValueError("duplicate disposition membership")
        if accepted & excluded or accepted | excluded != set(ordered):
            raise ValueError("disposition must account for every case exactly once")
        if (
            tuple(case for case in ordered if case in accepted)
            != self.accepted_case_ids
            or tuple(case for case in ordered if case in excluded)
            != self.excluded_case_ids
        ):
            raise ValueError("disposition subsets must retain original order")
        expected = (
            "NOT_EVALUABLE"
            if not accepted
            else "COMPLETE_WITH_EXCLUSIONS"
            if excluded
            else "COMPLETE_ALL_ACCEPTED"
        )
        if self.status != expected:
            raise ValueError("disposition status differs from denominator")
        return self


class _ReviewCaseBinding(AICaseSpec):
    """Internal integrity binding, with no eligibility or inclusion claim."""

    review_protocol_sha256: Digest
    review_evidence_sha256: Digest
    review_evidence: MigrationEvidencePin


def load_stage_canonical_roster(
    roster_path: Path,
    *,
    review_evidence_root: Path,
    protocol_path: Path,
    disposition_path: Path | None = None,
) -> tuple[StageCanonicalCase, ...]:
    if disposition_path is None:
        return _load_stage_review_chain(
            roster_path,
            review_evidence_root=review_evidence_root,
            protocol_path=protocol_path,
        )
    root = review_evidence_root.resolve()
    manifest = StageReviewDispositionManifest.model_validate_json(
        disposition_path.read_bytes()
    )
    protocol_raw = _pinned(root, manifest.protocol)
    if protocol_raw != protocol_path.read_bytes():
        raise ValueError("disposition protocol differs")
    protocol = StageReviewProtocol.model_validate_json(protocol_raw)
    specs = tuple(
        AICaseSpec.model_validate_json(_pinned(root, pin))
        for pin in protocol.case_inputs
    )
    if tuple(entry.case_id for entry in manifest.cases) != tuple(
        spec.case_id for spec in specs
    ):
        raise ValueError("disposition omits or reorders protocol cases")
    bindings = []
    for entry, spec in zip(manifest.cases, specs, strict=True):
        payload = spec.model_dump(mode="json")
        bindings.append(
            _ReviewCaseBinding(
                **payload,
                review_protocol_sha256=manifest.protocol.sha256,
                review_evidence_sha256=entry.review_evidence.sha256,
                review_evidence=entry.review_evidence,
            )
        )
    _load_stage_review_chain(
        roster_path,
        review_evidence_root=root,
        protocol_path=protocol_path,
        reviewed_bindings=tuple(bindings),
        require_inclusion=False,
    )
    accepted = []
    for entry in manifest.cases:
        evidence = StageReviewEvidence.model_validate_json(
            _pinned(root, entry.review_evidence)
        )
        responses = []
        for capture_pin in evidence.captures:
            capture = StageReviewCapture.model_validate_json(_pinned(root, capture_pin))
            responses.append(
                StageReviewResponse.model_validate_json(
                    _pinned(root, capture.exact_final)
                )
            )
        if all(
            response.decision == "include" and not response.pre_generation_blockers
            for response in responses
        ):
            accepted.append(entry.case_id)
    if tuple(accepted) != manifest.accepted_case_ids:
        raise ValueError("disposition membership contradicts sealed role decisions")
    cases = tuple(
        StageCanonicalCase.model_validate_json(line)
        for line in roster_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if tuple(case.case_id for case in cases) != manifest.accepted_case_ids:
        raise ValueError("canonical roster must equal accepted disposition subset")
    binding_by_id = {binding.case_id: binding for binding in bindings}
    for case in cases:
        binding = binding_by_id[case.case_id]
        fields = set(_ReviewCaseBinding.model_fields) - {"schema_version"}
        if any(getattr(case, name) != getattr(binding, name) for name in fields):
            raise ValueError("accepted canonical case differs from reviewed binding")
    # Full integrity proof above covers every excluded case; retained categories
    # for accepted rows are compared directly against all three sealed finals.
    for case in cases:
        evidence = StageReviewEvidence.model_validate_json(
            _pinned(root, case.review_evidence)
        )
        responses = {}
        for capture_pin in evidence.captures:
            capture = StageReviewCapture.model_validate_json(_pinned(root, capture_pin))
            response = StageReviewResponse.model_validate_json(
                _pinned(root, capture.exact_final)
            )
            responses[response.role] = response
        for field in CATEGORY_FIELDS[1:]:
            retained = []
            for role in ROLES:
                for issue in getattr(responses[role], field):
                    if issue not in retained:
                        retained.append(issue)
            if getattr(case, field) != tuple(retained):
                raise ValueError(
                    "accepted canonical case dropped reviewed obligations or limitations"
                )
    return cases
