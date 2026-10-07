"""Additive generation contracts for stage-reviewed validation-pending cases.

No provider is called here. Model proposals contain neither run identity nor
telemetry. The host owns capture identity; retained captures are integrity
evidence, not external attestations of provider identity or resource usage.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from cobol_archaeologist.migration.ai_review import (
    Digest,
    StrictModel,
    model_sha256,
)
from cobol_archaeologist.migration.contracts import (
    MigrationEvidencePin,
    MigrationFinding,
    MigrationTrack,
    ProviderIdentity,
)
from cobol_archaeologist.migration.successor import (
    PROPOSAL_ADAPTER,
    AbstentionProposal,
    Configuration4Binding,
    MigrationProposal,
)
from cobol_archaeologist.migration.successor import (
    build_successor_prompt as legacy_build_successor_prompt,
)

if __package__:
    from .stage_review_contracts import (
        ACCEPTANCE_POLICY,
        MANDATORY_VALIDATION,
        StageCanonicalCase,
    )
else:
    from stage_review_contracts import (
        ACCEPTANCE_POLICY,
        MANDATORY_VALIDATION,
        StageCanonicalCase,
    )


class StageSuccessorMethodIdentity(StrictModel):
    protocol_version: Literal["migration-stage-successor-agent-v1"] = (
        "migration-stage-successor-agent-v1"
    )
    request_schema: Literal["migration-stage-successor-request-v1"] = (
        "migration-stage-successor-request-v1"
    )
    response_schema: Literal["migration-successor-proposal-v1"] = (
        "migration-successor-proposal-v1"
    )
    codex_cli_version: str = Field(min_length=1)
    runner_sha256: Digest
    runtime_source_sha256: Digest
    validator_sha256: Digest
    backend_sha256: Digest
    validation_protocol_sha256: Digest
    max_turns: int = Field(ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)


class SchemaHashes(StrictModel):
    request: Digest
    response: Digest


class StageSuccessorMigrationRequest(StrictModel):
    schema_version: Literal["migration-stage-successor-request-v1"] = (
        "migration-stage-successor-request-v1"
    )
    track: Literal[MigrationTrack.ORACLE_ASSISTED] = MigrationTrack.ORACLE_ASSISTED
    case: StageCanonicalCase
    execution_purpose: Literal["official", "qualification"] = "official"
    finding: MigrationFinding
    provider: ProviderIdentity = Field(default_factory=ProviderIdentity)
    method: StageSuccessorMethodIdentity
    detector: Configuration4Binding
    schema_sha256: SchemaHashes
    stage_policy: Literal["all_three_include_zero_pre_generation_blockers"] = (
        ACCEPTANCE_POLICY
    )
    mandatory_validation_obligations: tuple[str, ...] = MANDATORY_VALIDATION

    @model_validator(mode="after")
    def aligned(self):
        if (
            self.mandatory_validation_obligations != MANDATORY_VALIDATION
            or self.mandatory_validation_obligations
            != self.case.mandatory_validation_obligations
            or self.stage_policy != self.case.acceptance_policy
        ):
            raise ValueError("stage policy and mandatory validation obligations differ")
        if self.finding.origin != self.track:
            raise ValueError("successor finding must be oracle-assisted")
        if (
            self.finding.prediction.instance_id != self.case.instance_id
            or self.finding.prediction.drift_type != self.case.drift_type
        ):
            raise ValueError("finding case identity differs")
        if (
            self.method.validation_protocol_sha256
            != self.case.validation_protocol_sha256
        ):
            raise ValueError("case and method validation protocol differ")
        if self.case.review_evidence_sha256 != self.case.review_evidence.sha256:
            raise ValueError("case review evidence pins differ")
        if self.schema_sha256.model_dump() != successor_schema_hashes():
            raise ValueError("successor request or response schema identity differs")
        return self


SYSTEM_PROMPT = """You are a COBOL remediation agent operating on one AI-reviewed
oracle-assisted case eligible for generation with validation pending. Use only the authorized finding and staged source files.
Work only inside the staged case directory. Never inspect credentials, git
history, mutation provenance, hidden labels, review records, fixtures, or another
case. Emit one minimal modification-only unified diff within the allowed source
scope, or explicitly abstain. Preserve program/copybook boundaries. A separate
validator decides safety and behavior. Return only the supplied JSON output
contract. Do not author provider usage, run identity, or host attestation."""


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hash(value) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


# Public compatibility names select only the new stage models, never v1 casts.
SuccessorMethodIdentity = StageSuccessorMethodIdentity
SuccessorMigrationRequest = StageSuccessorMigrationRequest
StageSuccessorRequest = StageSuccessorMigrationRequest


def successor_schema_hashes() -> dict[str, str]:
    return {
        "request": _hash(SuccessorMigrationRequest.model_json_schema()),
        "response": _hash(PROPOSAL_ADAPTER.json_schema()),
    }


def build_successor_prompt(request: SuccessorMigrationRequest) -> str:
    """Reuse the frozen whitelist, removing the private prediction label field."""
    prefix, payload = legacy_build_successor_prompt(request).split("\n", 1)
    visible = json.loads(payload)
    # DECISION: an oracle finding's structured labels are host evidence, not
    # generation input. Retain the authorized clause, source locus and rationale.
    visible["verified_finding"]["prediction"].pop("labels", None)
    return prefix + "\n" + _json(visible).decode()


def successor_run_key(request: SuccessorMigrationRequest) -> str:
    return _hash(
        {
            "request": request.model_dump(mode="json"),
            "schema_sha256": successor_schema_hashes(),
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": build_successor_prompt(request),
        }
    )


class StageSuccessorCapture(StrictModel):
    """Host-authored integrity envelope, separate from the untrusted proposal."""

    schema_version: Literal["migration-stage-successor-capture-v1"] = (
        "migration-stage-successor-capture-v1"
    )
    provenance: Literal["host_captured_session"] = "host_captured_session"
    execution_purpose: Literal["official", "qualification"] = "official"
    run_key: Digest
    request_sha256: Digest
    case_id: str
    track: Literal[MigrationTrack.ORACLE_ASSISTED] = MigrationTrack.ORACLE_ASSISTED
    provider: ProviderIdentity
    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    exact_final_sha256: Digest
    proposal_sha256: Digest
    proposal: MigrationProposal
    host_events: MigrationEvidencePin
    raw_transcript: MigrationEvidencePin
    provider_usage: Literal["not_recorded"] = "not_recorded"
    identity_limitations: Literal["host_capture_not_external_identity_attestation"] = (
        "host_capture_not_external_identity_attestation"
    )

    @model_validator(mode="after")
    def integrity(self):
        if self.completed_at <= self.started_at:
            raise ValueError("capture completion must follow start")
        if self.proposal_sha256 != model_sha256(self.proposal):
            raise ValueError("captured proposal hash differs")
        return self


SuccessorCapture = StageSuccessorCapture


def capture_successor_final(
    request: SuccessorMigrationRequest,
    exact_final: bytes,
    **host_fields,
) -> SuccessorCapture:
    """Parse the exact model final; bind host fields without inventing telemetry."""
    proposal = PROPOSAL_ADAPTER.validate_json(exact_final)
    return SuccessorCapture(
        run_key=successor_run_key(request),
        request_sha256=model_sha256(request),
        case_id=request.case.case_id,
        execution_purpose=request.execution_purpose,
        provider=request.provider,
        exact_final_sha256=hashlib.sha256(exact_final).hexdigest(),
        proposal_sha256=model_sha256(proposal),
        proposal=proposal,
        **host_fields,
    )


def validate_capture_identity(
    request: SuccessorMigrationRequest, capture: SuccessorCapture
) -> None:
    if (
        capture.run_key != successor_run_key(request)
        or capture.request_sha256 != model_sha256(request)
        or capture.case_id != request.case.case_id
        or capture.track != request.track
        or capture.provider != request.provider
        or capture.execution_purpose != request.execution_purpose
    ):
        raise ValueError("successor capture identity differs from frozen request")


def _read_pin(root: Path, pin: MigrationEvidencePin) -> bytes:
    root = root.resolve()
    path = root / pin.path
    resolved = path.resolve()
    resolved.relative_to(root)
    if any(
        p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents
    ):
        raise ValueError("symlink evidence is forbidden")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin.sha256:
        raise ValueError(f"evidence hash mismatch: {pin.path}")
    return raw


def validate_configuration4_binding(
    binding: Configuration4Binding, *, evidence_root: Path
) -> None:
    """Check the actual pinned intake artifacts before freezing generation."""
    _read_pin(evidence_root, binding.evaluation_manifest)
    decision = json.loads(_read_pin(evidence_root, binding.detector_decision))
    roster = json.loads(_read_pin(evidence_root, binding.input_roster))
    if (
        decision.get("schema_version") != "configuration-4-detector-decision-v1"
        or decision.get("configuration") != 4
        or decision.get("status") != "NOT_EVALUABLE"
    ):
        raise ValueError("configuration-4 detector decision differs")
    if (
        roster.get("configuration") != 4
        or roster.get("decision") != binding.detector_decision.model_dump(mode="json")
        or roster.get("detector_led")
        != {"active": False, "count": 0, "eligible_findings": []}
    ):
        raise ValueError(
            "configuration-4 intake must have zero inactive detector findings"
        )


def replay_successor_capture(
    request: SuccessorMigrationRequest,
    capture: SuccessorCapture,
    *,
    exact_final: bytes,
    evidence_root: Path,
) -> None:
    """Reconcile preserved final bytes and host evidence with the capture."""
    validate_capture_identity(request, capture)
    if hashlib.sha256(exact_final).hexdigest() != capture.exact_final_sha256:
        raise ValueError("exact final hash differs from capture")
    if PROPOSAL_ADAPTER.validate_json(exact_final) != capture.proposal:
        raise ValueError("exact final proposal differs from capture")
    _read_pin(evidence_root, capture.host_events)
    _read_pin(evidence_root, capture.raw_transcript)


def stage_successor_sources(
    request: SuccessorMigrationRequest,
    *,
    canonical_root: Path,
    staging_root: Path,
) -> Path:
    """Stage only exact authorized sources in a fresh run directory."""
    canonical = canonical_root.resolve()
    stage = staging_root.resolve() / successor_run_key(request)
    stage.mkdir(parents=True, exist_ok=False)
    try:
        for frozen in request.case.frozen_sources:
            source = canonical / frozen.path
            resolved = source.resolve()
            resolved.relative_to(canonical)
            if any(
                p.is_symlink()
                for p in (source, *source.parents)
                if p != canonical and canonical in p.parents
            ):
                raise ValueError("symlink source is forbidden")
            raw = resolved.read_bytes()
            if hashlib.sha256(raw).hexdigest() != frozen.sha256:
                raise ValueError(f"frozen source hash mismatch: {frozen.path}")
            target = stage / frozen.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    except Exception:
        shutil.rmtree(stage)
        raise
    return stage


class _StageValidationCase(StageCanonicalCase):
    """Private compatibility view; the property is never an artifact field."""

    @property
    def eligible_for_evaluation(self) -> bool:
        # DECISION: this legacy validator admission bit means reviewed enough
        # to attempt validation. Public stage artifacts retain validation pending.
        return self.eligible_for_generation


def validate_successor_migration(
    request: SuccessorMigrationRequest,
    capture: SuccessorCapture,
    *,
    base_files,
    backend,
):
    """Reuse every historical patch/backend gate after checking successor identity.

    The compatibility key exists only inside this call. No historical request,
    human review claim, PatchArtifact, or RunUsage is created or serialized.
    The backend receives the actual AI canonical case and the returned record
    retains the successor key.
    """
    from cobol_archaeologist.migration.agent import migration_run_key
    from cobol_archaeologist.migration.validate import validate_migration

    validate_capture_identity(request, capture)
    # DECISION: A private structural adapter reuses the frozen validator without
    # relabeling AI review as human review or fabricating legacy usage fields.
    proposal = capture.proposal
    abstained = isinstance(proposal, AbstentionProposal)
    adapter = SimpleNamespace(
        run_key=migration_run_key(request),
        case_id=request.case.case_id,
        track=request.track,
        abstained=abstained,
        patch=None if abstained else proposal.patch,
        rationale=None if abstained else proposal.rationale,
        intended_behavior=None if abstained else proposal.intended_behavior,
        affected_locations=() if abstained else proposal.affected_locations,
        abstention_reason=proposal.reason if abstained else None,
    )
    validation_case = _StageValidationCase.model_validate(
        request.case.model_dump(mode="json")
    )
    validation_request = request.model_copy(update={"case": validation_case})
    result = validate_migration(
        validation_request,
        adapter,
        expected_track=MigrationTrack.ORACLE_ASSISTED,
        base_files=base_files,
        backend=backend,
    )
    return result.model_copy(update={"run_key": capture.run_key})
