"""Frozen data contracts for the T6 migration evaluation.

These models deliberately keep generation and validation separate.  A model
may propose a patch, but only :mod:`cobol_archaeologist.migration.validate`
can assign validation outcomes.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.schemas import DriftPrediction, RegulationClause

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MigrationTrack(StrEnum):
    """Tracks that must remain separate in every artifact and report."""

    DETECTOR_LED = "detector_led"
    ORACLE_ASSISTED = "oracle_assisted"


class ValidationCapability(StrEnum):
    """Strongest validation available for a frozen migration case."""

    BATCH_EXECUTABLE = "batch_executable"
    CICS_STATIC = "cics_static"
    COPYBOOK_FANOUT = "copybook_fanout"


class CaseStratum(StrEnum):
    LOCAL = "local"
    INTERPROCEDURAL = "interprocedural"


class CandidateReviewState(StrEnum):
    HUMAN_REVIEW_PENDING = "human_review_pending"


class CanonicalReviewState(StrEnum):
    HUMAN_PRIMARY_REVIEWED_AND_VERIFIED = "human_primary_reviewed_and_verified"


def normalized_relative_path(value: str) -> str:
    """Return a portable contained path, rejecting ambiguous spellings."""

    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if (
        not value
        or "\x00" in value
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        raise ValueError(f"path must be a contained relative path: {value!r}")
    return posix.as_posix()


class FrozenSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str

    @model_validator(mode="after")
    def _valid(self) -> FrozenSource:
        normalized = normalized_relative_path(self.path)
        if normalized != self.path:
            raise ValueError(f"path must use normalized POSIX spelling: {normalized!r}")
        if not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return self


class MigrationCandidate(BaseModel):
    """Gold-free roster selection; never sufficient to authorize evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-candidate-v1"] = "migration-candidate-v1"
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
    primary_program: str
    source_bundle_sha256: str
    frozen_sources: tuple[FrozenSource, ...] = Field(min_length=1)
    benchmark_row_sha256: str
    benchmark_inventory_sha256: str
    detector_visible_ref: str
    oracle_spec_ref: str
    selected_before_config3_results: Literal[True] = True
    review_state: Literal[CandidateReviewState.HUMAN_REVIEW_PENDING] = (
        CandidateReviewState.HUMAN_REVIEW_PENDING
    )
    independent_verification: Literal["pending"] = "pending"
    adjudication: Literal["not_started"] = "not_started"
    eligible_for_evaluation: Literal[False] = False
    selection_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _hashes(self) -> MigrationCandidate:
        for name, value in (
            ("source_bundle_sha256", self.source_bundle_sha256),
            ("benchmark_row_sha256", self.benchmark_row_sha256),
            ("benchmark_inventory_sha256", self.benchmark_inventory_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        return self


class DetectorVisibleCandidate(BaseModel):
    """Gold-free source/clause envelope awaiting a verified detector finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-detector-input-v1"] = (
        "migration-detector-input-v1"
    )
    case_id: str
    instance_id: str
    regulation_clause: RegulationClause
    primary_program: str
    source_bundle_sha256: str
    frozen_sources: tuple[FrozenSource, ...]
    verified_finding_status: Literal["pending_config3_utility_gate"] = (
        "pending_config3_utility_gate"
    )
    verified_finding: None = None


class OracleCandidateSpec(BaseModel):
    """Separated candidate oracle and behavioral checks, pending human review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-oracle-spec-v1"] = "migration-oracle-spec-v1"
    case_id: str
    instance_id: str
    oracle_prediction: DriftPrediction
    allowed_source_scope: tuple[AllowedSourceScope, ...] = Field(min_length=1)
    intended_behavior: BehaviorCheck
    unaffected_regressions: tuple[BehaviorCheck, ...] = Field(min_length=1)
    affected_hosts: tuple[str, ...] = ()
    review_state: Literal[CandidateReviewState.HUMAN_REVIEW_PENDING] = (
        CandidateReviewState.HUMAN_REVIEW_PENDING
    )
    eligible_for_evaluation: Literal[False] = False


class AllowedSourceScope(BaseModel):
    """A file and inclusive source-line spans the patch may modify."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    line_spans: tuple[tuple[int, int], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _valid(self) -> AllowedSourceScope:
        normalized = normalized_relative_path(self.path)
        if normalized != self.path:
            raise ValueError(f"path must use normalized POSIX spelling: {normalized!r}")
        for start, end in self.line_spans:
            if start < 1 or end < start:
                raise ValueError("line spans must be ordered, inclusive, and 1-based")
        return self


class BehaviorCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    description: str = Field(min_length=1)


class MigrationCase(BaseModel):
    """The public half of a roster row, frozen before patch generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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
    primary_program: str
    frozen_sources: tuple[FrozenSource, ...] = Field(min_length=1)
    allowed_source_scope: tuple[AllowedSourceScope, ...] = Field(min_length=1)
    intended_behavior: BehaviorCheck
    unaffected_regressions: tuple[BehaviorCheck, ...] = Field(min_length=1)
    affected_hosts: tuple[str, ...] = ()
    detector_input_ref: str
    oracle_evidence_ref: str
    review_protocol_sha256: str
    validation_protocol_sha256: str
    review_state: Literal[CanonicalReviewState.HUMAN_PRIMARY_REVIEWED_AND_VERIFIED]
    review_evidence_sha256: str
    eligible_for_evaluation: Literal[True]

    @model_validator(mode="after")
    def _scope_and_capability(self) -> MigrationCase:
        for name, value in (
            ("review_evidence_sha256", self.review_evidence_sha256),
            ("review_protocol_sha256", self.review_protocol_sha256),
            ("validation_protocol_sha256", self.validation_protocol_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        source_paths = [source.path for source in self.frozen_sources]
        if len(source_paths) != len(set(source_paths)):
            raise ValueError("frozen source paths must be unique")
        scope_paths = [scope.path for scope in self.allowed_source_scope]
        if len(scope_paths) != len(set(scope_paths)):
            raise ValueError("allowed source-scope paths must be unique")
        unknown = set(scope_paths) - set(source_paths)
        if unknown:
            raise ValueError(f"allowed scope names unfrozen sources: {sorted(unknown)}")
        if (
            self.validation_capability == ValidationCapability.COPYBOOK_FANOUT
            and not self.affected_hosts
        ):
            raise ValueError("copybook fan-out cases require affected_hosts")
        if (
            self.validation_capability != ValidationCapability.COPYBOOK_FANOUT
            and self.affected_hosts
        ):
            raise ValueError("affected_hosts belong only to copybook fan-out cases")
        return self


class MigrationEvidencePin(BaseModel):
    """Contained path and exact hash for an external migration artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str

    @model_validator(mode="after")
    def _valid(self) -> MigrationEvidencePin:
        normalized = normalized_relative_path(self.path)
        if normalized != self.path:
            raise ValueError(f"path must use normalized POSIX spelling: {normalized!r}")
        if not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase SHA-256 digest")
        return self


class ReviewerProtocolKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review_role: Literal["human_primary", "independent_verifier", "adjudicator"]
    reviewer_identity: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    public_key_ed25519: str = Field(pattern=r"^[0-9a-f]{64}$")


class MigrationReviewProtocol(BaseModel):
    """Pre-response reviewer key registry pinned by every canonical case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-review-protocol-v1"] = (
        "migration-review-protocol-v1"
    )
    state: Literal["ready"]
    frozen_before_responses: Literal[True]
    frozen_at: AwareDatetime
    runtime_source_sha256: str
    reviewer_keys: tuple[ReviewerProtocolKey, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _complete(self) -> MigrationReviewProtocol:
        if not _SHA256_RE.fullmatch(self.runtime_source_sha256):
            raise ValueError("runtime_source_sha256 must be a lowercase SHA-256 digest")
        roles = [key.review_role for key in self.reviewer_keys]
        identities = [key.reviewer_identity for key in self.reviewer_keys]
        key_ids = [key.key_id for key in self.reviewer_keys]
        if set(roles) != {"human_primary", "independent_verifier", "adjudicator"}:
            raise ValueError("review protocol must pin exactly one key for each role")
        if len(set(identities)) != 3 or len(set(key_ids)) != 3:
            raise ValueError("reviewer identities and key IDs must be distinct")
        return self


class MigrationValidationProtocol(BaseModel):
    """Pre-run validator/backend registry entry pinned by the canonical roster."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-validation-protocol-v1"] = (
        "migration-validation-protocol-v1"
    )
    state: Literal["ready"]
    frozen_before_runs: Literal[True]
    frozen_at: AwareDatetime
    runtime_source_sha256: str
    validator_sha256: str
    backend_id: str = Field(min_length=1)
    backend_module: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$")
    backend_qualname: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$")
    backend_sha256: str

    @model_validator(mode="after")
    def _hashes(self) -> MigrationValidationProtocol:
        for name, value in (
            ("runtime_source_sha256", self.runtime_source_sha256),
            ("validator_sha256", self.validator_sha256),
            ("backend_sha256", self.backend_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        return self


class MigrationReviewResponse(BaseModel):
    """One independently authored human review response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-review-response-v1"] = (
        "migration-review-response-v1"
    )
    case_id: str = Field(pattern=r"^migration_[a-z0-9_-]+$")
    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    review_role: Literal["human_primary", "independent_verifier", "adjudicator"]
    reviewer_identity: str = Field(min_length=1)
    completed_at: AwareDatetime
    decision: Literal["include"]
    rationale: str = Field(min_length=1)
    evidence: tuple[MigrationEvidencePin, ...] = Field(min_length=1)


class ExternalReviewerVerification(BaseModel):
    """Externally issued proof that a response came from the named human."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-reviewer-verification-v1"] = (
        "migration-reviewer-verification-v1"
    )
    review_role: Literal["human_primary", "independent_verifier", "adjudicator"]
    reviewer_identity: str = Field(min_length=1)
    response: MigrationEvidencePin
    identity_verified: Literal[True]
    human_reviewer_verified: Literal[True]
    verified_by_external_party: str = Field(min_length=1)
    verification_method: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    verified_at: AwareDatetime
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")

    @model_validator(mode="after")
    def _external(self) -> ExternalReviewerVerification:
        if self.verified_by_external_party == self.reviewer_identity:
            raise ValueError("a reviewer cannot externally verify their own identity")
        return self


class CanonicalReviewEvidence(BaseModel):
    """Pins for three human decisions and their external identity attestations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-review-evidence-v1"] = (
        "migration-review-evidence-v1"
    )
    case_id: str = Field(pattern=r"^migration_[a-z0-9_-]+$")
    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    human_primary_response: MigrationEvidencePin
    independent_verifier_response: MigrationEvidencePin
    adjudication_response: MigrationEvidencePin
    human_primary_identity_verification: MigrationEvidencePin
    independent_verifier_identity_verification: MigrationEvidencePin
    adjudicator_identity_verification: MigrationEvidencePin
    review_state: Literal[
        CanonicalReviewState.HUMAN_PRIMARY_REVIEWED_AND_VERIFIED
    ]
    eligible_for_evaluation: Literal[True]


class ValidationArtifactPin(BaseModel):
    """Immutable identity and content pin for one offline validation result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["migration-validation-pin-v1"] = (
        "migration-validation-pin-v1"
    )
    path: str
    sha256: str
    request_sha256: str
    artifact_sha256: str
    validator_sha256: str
    backend_sha256: str
    runtime_source_sha256: str
    run_key: str
    case_id: str
    track: MigrationTrack

    @model_validator(mode="after")
    def _valid(self) -> ValidationArtifactPin:
        normalized = normalized_relative_path(self.path)
        if normalized != self.path:
            raise ValueError(f"path must use normalized POSIX spelling: {normalized!r}")
        for name, value in (
            ("sha256", self.sha256),
            ("request_sha256", self.request_sha256),
            ("artifact_sha256", self.artifact_sha256),
            ("validator_sha256", self.validator_sha256),
            ("backend_sha256", self.backend_sha256),
            ("runtime_source_sha256", self.runtime_source_sha256),
            ("run_key", self.run_key),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        return self


class Configuration3DecisionArtifact(BaseModel):
    """Pinned release-utility decision controlling detector-led activation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-decision-v1"] = (
        "configuration-3-decision-v1"
    )
    configuration: Literal[3] = 3
    status: Literal["GO", "NO_GO", "NOT_EVALUABLE"]


class MigrationFinding(BaseModel):
    """Verified evidence made visible to one isolated migration task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: MigrationTrack
    prediction: DriftPrediction
    verifier_tier: Literal["executed", "static"]
    verifier_evidence: str = Field(min_length=1)
    evidence_ledger: tuple[str, ...] = Field(min_length=1)


class ProviderIdentity(BaseModel):
    """T6.2 identity lock; this package does not itself call the provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authentication: Literal["chatgpt"] = "chatgpt"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["max"] = "max"
    isolation: Literal["one_case_per_task"] = "one_case_per_task"


class MigrationMethodIdentity(BaseModel):
    """Complete method/runtime identity required before a patch can be requested."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal["migration-agent-v2"] = "migration-agent-v2"
    request_schema: Literal["migration-request-v2"] = "migration-request-v2"
    response_schema: Literal["migration-patch-artifact-v1"] = (
        "migration-patch-artifact-v1"
    )
    codex_cli_version: str = Field(min_length=1)
    runner_sha256: str
    runtime_source_sha256: str
    max_turns: int = Field(ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)

    @model_validator(mode="after")
    def _hashes(self) -> MigrationMethodIdentity:
        for name, value in (
            ("runner_sha256", self.runner_sha256),
            ("runtime_source_sha256", self.runtime_source_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        return self


class DetectorEvidenceBinding(BaseModel):
    """Identity pin for one verified configuration-3 detector record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configuration: Literal[3] = 3
    detector_records_sha256: str
    evaluation_record_sha256: str
    evaluation_run_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def _hashes(self) -> DetectorEvidenceBinding:
        for name, value in (
            ("detector_records_sha256", self.detector_records_sha256),
            ("evaluation_record_sha256", self.evaluation_record_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        return self


class MigrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track: MigrationTrack
    case: MigrationCase
    finding: MigrationFinding
    provider: ProviderIdentity = Field(default_factory=ProviderIdentity)
    method: MigrationMethodIdentity
    detector_evidence: DetectorEvidenceBinding | None = None

    @model_validator(mode="after")
    def _aligned(self) -> MigrationRequest:
        if self.finding.origin != self.track:
            raise ValueError("finding origin must match the evaluation track")
        prediction = self.finding.prediction
        if prediction.instance_id != self.case.instance_id:
            raise ValueError("finding and migration case instance IDs must match")
        if prediction.drift_type != self.case.drift_type:
            raise ValueError("finding and migration case drift classes must match")
        if self.track == MigrationTrack.DETECTOR_LED and self.detector_evidence is None:
            raise ValueError("detector-led requests require configuration-3 evidence")
        if self.track == MigrationTrack.ORACLE_ASSISTED and self.detector_evidence is not None:
            raise ValueError("oracle-assisted requests cannot carry detector evidence")
        return self


class AffectedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    line_span: tuple[int, int]

    @model_validator(mode="after")
    def _valid(self) -> AffectedLocation:
        normalized = normalized_relative_path(self.path)
        if normalized != self.path:
            raise ValueError(f"path must use normalized POSIX spelling: {normalized!r}")
        start, end = self.line_span
        if start < 1 or end < start:
            raise ValueError("line_span must be ordered, inclusive, and 1-based")
        return self


class RunUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turns: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    interruptions: int = Field(ge=0)
    resumed: bool


class PatchArtifact(BaseModel):
    """Untrusted model output; validation fields are intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str
    track: MigrationTrack
    patch: str | None = None
    rationale: str | None = None
    intended_behavior: str | None = None
    affected_locations: tuple[AffectedLocation, ...] = ()
    abstained: bool
    abstention_reason: str | None = None
    usage: RunUsage

    @model_validator(mode="after")
    def _patch_or_abstention(self) -> PatchArtifact:
        if self.abstained:
            if self.patch is not None or self.affected_locations:
                raise ValueError(
                    "an abstention cannot include a patch or affected locations"
                )
            if not self.abstention_reason:
                raise ValueError("an abstention requires an explicit reason")
        else:
            if not self.patch or not self.patch.strip():
                raise ValueError("a non-abstention requires a patch")
            if not self.rationale or not self.intended_behavior:
                raise ValueError("a patch requires rationale and intended behavior")
            if not self.affected_locations:
                raise ValueError("a patch requires affected locations")
            if self.abstention_reason is not None:
                raise ValueError("a patch cannot carry an abstention reason")
        return self
