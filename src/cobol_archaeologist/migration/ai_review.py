"""Additive, explicitly nonhuman migration review and promotion gates.

Host capture pins establish retained evidence integrity, not remote identity
attestation or independence of model errors. Historical human review is separate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.migration.contracts import (
    AllowedSourceScope,
    BehaviorCheck,
    CaseStratum,
    FrozenSource,
    MigrationEvidencePin,
    ValidationCapability,
    normalized_relative_path,
)

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Role = Literal["ai_primary", "independent_ai_verifier", "ai_adjudicator"]
ROLES = ("ai_primary", "independent_ai_verifier", "ai_adjudicator")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AIReviewerIdentity(StrictModel):
    role: Role
    model: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    transport: Literal["collaboration_subagent"] = "collaboration_subagent"
    nonhuman: Literal[True] = True


class AICaseSpec(StrictModel):
    schema_version: Literal["migration-ai-review-case-input-v1"] = (
        "migration-ai-review-case-input-v1"
    )
    case_id: str = Field(pattern=r"^migration_[a-z0-9_-]+$")
    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    drift_type: Literal[
        "D1_stale_threshold",
        "D2_missing_rule",
        "D3_contradictory",
        "D4_stale_reference_data",
        "D5_boundary_error",
        "D6_dead_code",
    ]
    stratum: CaseStratum
    validation_capability: ValidationCapability
    primary_program: str = Field(min_length=1)
    frozen_sources: tuple[FrozenSource, ...] = Field(min_length=1)
    source_evidence: tuple[MigrationEvidencePin, ...] = Field(min_length=1)
    regulation_evidence: MigrationEvidencePin
    fixture_evidence: tuple[MigrationEvidencePin, ...] = Field(min_length=1)
    allowed_source_scope: tuple[AllowedSourceScope, ...] = Field(min_length=1)
    intended_behavior: BehaviorCheck
    unaffected_regressions: tuple[BehaviorCheck, ...] = Field(min_length=1)
    affected_hosts: tuple[str, ...] = ()
    detector_input_ref: str
    oracle_evidence_ref: str
    validation_protocol_sha256: Digest
    source_bundle_group: str = Field(min_length=1)
    duplicate_source_justification: str = Field(min_length=1)

    @model_validator(mode="after")
    def scope(self):
        paths = [source.path for source in self.frozen_sources]
        scopes = [scope.path for scope in self.allowed_source_scope]
        if len(paths) != len(set(paths)) or len(scopes) != len(set(scopes)):
            raise ValueError("duplicate source or scope paths")
        if set(scopes) - set(paths):
            raise ValueError("scope names an unfrozen source")
        if len(self.source_evidence) != len(self.frozen_sources):
            raise ValueError("source evidence must bind every source")
        if tuple(pin.sha256 for pin in self.source_evidence) != tuple(
            source.sha256 for source in self.frozen_sources
        ):
            raise ValueError("source evidence hashes differ from frozen sources")
        for refs in (self.source_evidence, self.fixture_evidence):
            if len({pin.path for pin in refs}) != len(refs):
                raise ValueError("duplicate evidence paths")
        checks = [
            self.intended_behavior.check_id,
            *(check.check_id for check in self.unaffected_regressions),
        ]
        if len(checks) != len(set(checks)):
            raise ValueError("duplicate behavioral check IDs")
        if (self.validation_capability == ValidationCapability.COPYBOOK_FANOUT) != bool(
            self.affected_hosts
        ):
            raise ValueError("copybook fanout alone requires affected hosts")
        for ref in (self.detector_input_ref, self.oracle_evidence_ref):
            if normalized_relative_path(ref) != ref:
                raise ValueError("noncanonical evidence reference")
        return self


class AIReviewProtocol(StrictModel):
    schema_version: Literal["migration-ai-review-protocol-v1"] = (
        "migration-ai-review-protocol-v1"
    )
    frozen_at: AwareDatetime
    authorization_evidence: MigrationEvidencePin
    candidate_manifest: MigrationEvidencePin
    runtime_source_sha256: Digest
    response_schema_sha256: Digest
    case_inputs: tuple[MigrationEvidencePin, ...] = Field(min_length=1)
    reviewers: tuple[AIReviewerIdentity, ...] = Field(min_length=3, max_length=3)
    review_provenance: Literal[
        "ai_primary_independent_ai_verification_and_adjudication"
    ] = "ai_primary_independent_ai_verification_and_adjudication"
    nonhuman: Literal[True] = True

    @model_validator(mode="after")
    def unique(self):
        if {r.role for r in self.reviewers} != set(ROLES):
            raise ValueError("exactly three distinct AI roles required")
        if len({p.path for p in self.case_inputs}) != len(self.case_inputs):
            raise ValueError("duplicate case input paths")
        return self


class AIReviewRequest(StrictModel):
    schema_version: Literal["migration-ai-review-request-v1"] = (
        "migration-ai-review-request-v1"
    )
    case_id: str
    reviewer: AIReviewerIdentity
    protocol: MigrationEvidencePin
    case_input: MigrationEvidencePin
    prompt: MigrationEvidencePin
    response_schema_sha256: Digest
    prior_responses: tuple[MigrationEvidencePin, ...] = ()

    @model_validator(mode="after")
    def isolation(self):
        if self.reviewer.role != "ai_adjudicator" and self.prior_responses:
            raise ValueError("primary and verifier must be blind to prior responses")
        if self.reviewer.role == "ai_adjudicator" and len(self.prior_responses) != 2:
            raise ValueError("adjudicator must bind both sealed independent responses")
        return self


def model_sha256(model: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def response_schema_sha256() -> str:
    return hashlib.sha256(
        json.dumps(
            AIReviewResponse.model_json_schema(), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


class AIReviewResponse(StrictModel):
    schema_version: Literal["migration-ai-review-response-v1"] = (
        "migration-ai-review-response-v1"
    )
    case_id: str
    role: Role
    decision: Literal["include", "exclude", "needs_revision"]
    rationale: str = Field(min_length=1)
    scope_judgment: str = Field(min_length=1)
    intended_fixture_judgment: str = Field(min_length=1)
    regression_fixture_judgment: str = Field(min_length=1)
    capability_judgment: str = Field(min_length=1)
    duplicate_source_judgment: str = Field(min_length=1)
    unresolved_issues: tuple[str, ...] = ()
    evidence: tuple[MigrationEvidencePin, ...] = Field(min_length=1)


def validate_response_evidence(
    response: AIReviewResponse,
    required: tuple[MigrationEvidencePin, ...],
    request: AIReviewRequest,
) -> None:
    """Accept exact case citations, optionally both bound adjudication finals."""
    expected = {(p.path, p.sha256) for p in required}
    actual = [(p.path, p.sha256) for p in response.evidence]
    allowed = [expected]
    if request.reviewer.role == "ai_adjudicator":
        # DECISION: prior-final citations are optional as a complete pair. Keep
        # earlier source-only finals valid; never accept unbound/partial extras.
        allowed.append(expected | {(p.path, p.sha256) for p in request.prior_responses})
    if len(actual) != len(set(actual)) or set(actual) not in allowed:
        raise ValueError("response lacks exact case source/fixture evidence or has unbound citations")


class AIHostSessionEvents(StrictModel):
    """Normalized host capture, never a model-authored identity assertion."""

    schema_version: Literal["migration-ai-host-session-events-v1"] = (
        "migration-ai-host-session-events-v1"
    )
    provenance: Literal["host_captured_collaboration_session"]
    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    reviewer: AIReviewerIdentity
    request_sha256: Digest
    final_sha256: Digest
    started_at: AwareDatetime
    completed_at: AwareDatetime
    raw_transcript: MigrationEvidencePin


class AIReviewCapture(StrictModel):
    schema_version: Literal["migration-ai-review-capture-v1"] = (
        "migration-ai-review-capture-v1"
    )
    request: MigrationEvidencePin
    request_sha256: Digest
    exact_final: MigrationEvidencePin
    host_events: MigrationEvidencePin
    provider_usage: Literal["not_recorded"] = "not_recorded"
    identity_limitations: Literal["host_capture_not_external_identity_attestation"] = (
        "host_capture_not_external_identity_attestation"
    )


class AIReviewEvidence(StrictModel):
    schema_version: Literal["migration-ai-review-evidence-v1"] = (
        "migration-ai-review-evidence-v1"
    )
    case_id: str
    case_input: MigrationEvidencePin
    protocol: MigrationEvidencePin
    captures: tuple[MigrationEvidencePin, ...] = Field(min_length=3, max_length=3)
    review_provenance: Literal[
        "ai_primary_independent_ai_verification_and_adjudication"
    ] = "ai_primary_independent_ai_verification_and_adjudication"
    nonhuman: Literal[True] = True


class AICanonicalMigrationCase(AICaseSpec):
    schema_version: Literal["migration-ai-reviewed-case-v1"] = (
        "migration-ai-reviewed-case-v1"
    )
    review_protocol_sha256: Digest
    review_evidence_sha256: Digest
    review_evidence: MigrationEvidencePin
    review_state: Literal["ai_primary_reviewed_verified_and_adjudicated"] = (
        "ai_primary_reviewed_verified_and_adjudicated"
    )
    review_provenance: Literal[
        "ai_primary_independent_ai_verification_and_adjudication"
    ] = "ai_primary_independent_ai_verification_and_adjudication"
    eligible_for_evaluation: Literal[True] = True
    nonhuman: Literal[True] = True


def _pinned(root: Path, pin: MigrationEvidencePin) -> bytes:
    root = root.resolve()
    path = root / pin.path
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("review evidence path escapes root")
    if any(
        parent.is_symlink()
        for parent in (path, *path.parents)
        if parent != root and root in parent.parents
    ):
        raise ValueError("symlink review evidence is forbidden")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin.sha256:
        raise ValueError(f"review evidence checksum mismatch: {pin.path}")
    return raw


def _load_review_chain(
    roster_path: Path,
    *,
    review_evidence_root: Path,
    protocol_path: Path,
    reviewed_bindings: tuple | None = None,
    require_inclusion: bool = True,
) -> tuple[AICanonicalMigrationCase, ...]:
    root = review_evidence_root.resolve()
    protocol_raw = protocol_path.read_bytes()
    protocol_hash = hashlib.sha256(protocol_raw).hexdigest()
    protocol = AIReviewProtocol.model_validate_json(protocol_raw)
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
            AICanonicalMigrationCase.model_validate_json(line)
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
    used_sessions, used_tasks = set(), set()
    for case in cases:
        if (
            case.review_protocol_sha256 != protocol_hash
            or case.review_evidence_sha256 != case.review_evidence.sha256
        ):
            raise ValueError("canonical case review pins differ")
        evidence = AIReviewEvidence.model_validate_json(
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
        required = (
            *spec.source_evidence,
            spec.regulation_evidence,
            *spec.fixture_evidence,
        )
        for pin in required:
            _pinned(root, pin)
        responses, event_by_role = {}, {}
        for capture_pin in evidence.captures:
            capture = AIReviewCapture.model_validate_json(_pinned(root, capture_pin))
            request = AIReviewRequest.model_validate_json(
                _pinned(root, capture.request)
            )
            events = AIHostSessionEvents.model_validate_json(
                _pinned(root, capture.host_events)
            )
            final_raw = _pinned(root, capture.exact_final)
            response = AIReviewResponse.model_validate_json(final_raw)
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
            if events.session_id in used_sessions or events.task_id in used_tasks:
                raise ValueError("reused review task or session")
            used_sessions.add(events.session_id)
            used_tasks.add(events.task_id)
            if not protocol.frozen_at < events.started_at < events.completed_at:
                raise ValueError("review capture timing differs from freeze")
            _pinned(root, events.raw_transcript)
            _pinned(root, request.prompt)
            if response.case_id != case.case_id or response.role != role:
                raise ValueError("response case or role differs")
            validate_response_evidence(response, required, request)
            if require_inclusion and (
                response.decision != "include" or response.unresolved_issues
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
    return cases


class AIReviewDispositionEntry(StrictModel):
    case_id: str
    review_evidence: MigrationEvidencePin


class AIReviewDispositionManifest(StrictModel):
    """Exhaustive accounting grounded in preserved exact review finals."""

    schema_version: Literal["migration-ai-review-disposition-v1"] = (
        "migration-ai-review-disposition-v1"
    )
    protocol: MigrationEvidencePin
    cases: tuple[AIReviewDispositionEntry, ...] = Field(min_length=1)
    accepted_case_ids: tuple[str, ...]
    excluded_case_ids: tuple[str, ...]
    status: Literal[
        "COMPLETE_ALL_ACCEPTED", "COMPLETE_WITH_EXCLUSIONS", "NOT_EVALUABLE"
    ]
    acceptance_policy: Literal["all_three_include_no_unresolved_issues"] = (
        "all_three_include_no_unresolved_issues"
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


def load_ai_canonical_roster(
    roster_path: Path,
    *,
    review_evidence_root: Path,
    protocol_path: Path,
    disposition_path: Path | None = None,
) -> tuple[AICanonicalMigrationCase, ...]:
    if disposition_path is None:
        return _load_review_chain(
            roster_path,
            review_evidence_root=review_evidence_root,
            protocol_path=protocol_path,
        )
    root = review_evidence_root.resolve()
    manifest = AIReviewDispositionManifest.model_validate_json(
        disposition_path.read_bytes()
    )
    protocol_raw = _pinned(root, manifest.protocol)
    if protocol_raw != protocol_path.read_bytes():
        raise ValueError("disposition protocol differs")
    protocol = AIReviewProtocol.model_validate_json(protocol_raw)
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
    _load_review_chain(
        roster_path,
        review_evidence_root=root,
        protocol_path=protocol_path,
        reviewed_bindings=tuple(bindings),
        require_inclusion=False,
    )
    accepted = []
    for entry in manifest.cases:
        evidence = AIReviewEvidence.model_validate_json(
            _pinned(root, entry.review_evidence)
        )
        responses = []
        for capture_pin in evidence.captures:
            capture = AIReviewCapture.model_validate_json(_pinned(root, capture_pin))
            responses.append(
                AIReviewResponse.model_validate_json(_pinned(root, capture.exact_final))
            )
        if all(
            response.decision == "include" and not response.unresolved_issues
            for response in responses
        ):
            accepted.append(entry.case_id)
    if tuple(accepted) != manifest.accepted_case_ids:
        raise ValueError("disposition membership contradicts sealed role decisions")
    cases = tuple(
        AICanonicalMigrationCase.model_validate_json(line)
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
    return cases
