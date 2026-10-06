"""Fail-closed preparation and validation for the T6-v2 temporal add-on.

The preparation manifest deliberately separates the nine independently reviewed
v1 pairs from eleven *design specifications*.  A design specification is not a
labelled pair and cannot enter evaluation until human-primary review, a separate
verification pass, and any required adjudication are recorded in a later freeze.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from cobol_archaeologist.schemas import (
    CodeLocus,
    DriftInstance,
    DriftType,
    Labels,
    RegulationClause,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Period = Literal["P3", "P4", "P5"]


class ArtifactPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: Sha256


class AuthorityPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_role: str = Field(min_length=1)
    file: str = Field(min_length=1)
    sha256: Sha256


class CandidateProgramPin(ArtifactPin):
    model_config = ConfigDict(extra="forbid")

    pair_id: str = Field(pattern=r"^t6v2-candidate-\d{2}$")


class RowReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    row_sha256: Sha256
    version: str = Field(min_length=1)
    effective_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    expected_drift_type: str = Field(pattern=r"^D[1-7]_")


class CarriedForwardPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str = Field(pattern=r"^t6v2-carried-\d{2}$")
    period: Literal["P4", "P5"]
    source_split: Literal["data/benchmark/v1/test.jsonl"]
    sides: tuple[RowReference, RowReference]
    code_input_path: str = Field(pattern=r"^data/benchmark/seed/programs/.+\.cbl$")
    code_sha256: Sha256
    review_state: Literal["v1_independently_reviewed"]
    eligible_for_evaluation: Literal[True]


class CandidateAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_role: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    effective_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CandidatePairSpec(BaseModel):
    """A proposed pair shape, intentionally incapable of claiming review."""

    model_config = ConfigDict(extra="forbid")

    pair_id: str = Field(pattern=r"^t6v2-candidate-\d{2}$")
    origin: Literal["new_pair_design"]
    period: Period
    planned_code_input: str = Field(pattern=r"^T6V2P[345][A-Z0-9]+\.cbl$")
    locality: Literal["local", "interprocedural"]
    implementation_shape: str = Field(min_length=20)
    old_authority: CandidateAuthority
    new_authority: CandidateAuthority
    review_state: Literal["candidate_unreviewed"]
    human_primary_review: None = None
    independent_verification: None = None
    adjudication: None = None
    eligible_for_evaluation: Literal[False] = False
    development_use_prohibited: Literal[True] = True

    @model_validator(mode="after")
    def _authority_versions_differ(self) -> CandidatePairSpec:
        old_axis = (self.old_authority.version, self.old_authority.effective_date)
        new_axis = (self.new_authority.version, self.new_authority.effective_date)
        if old_axis == new_axis:
            raise ValueError("candidate sides must pin different temporal versions")
        if self.old_authority.source_role == self.new_authority.source_role:
            raise ValueError("candidate sides must pin distinct source roles")
        return self


class CandidateSideProposal(BaseModel):
    """A sealed proposal for one temporal side, never a reviewed gold row."""

    model_config = ConfigDict(extra="forbid")

    candidate_side_id: str = Field(pattern=r"^t6v2-candidate-\d{2}-[ab]$")
    blind_review_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    authority: RegulationClause
    code_locus: CodeLocus
    proposed_drift_type: DriftType
    proposed_labels: Labels
    proposal_rationale: str = Field(min_length=20)

    @model_validator(mode="after")
    def _proposal_labels_and_locus_agree(self) -> CandidateSideProposal:
        conformant = self.proposed_drift_type == "D7_conformant"
        if conformant:
            if (
                self.proposed_labels.program_level != "conformant"
                or self.proposed_labels.paragraph_level != "conformant"
                or self.proposed_labels.line_level
            ):
                raise ValueError("D7 proposal must carry conformant empty labels")
        elif self.proposed_labels.program_level != "drift":
            raise ValueError("non-D7 proposal must carry a drift program label")

        for ref in self.proposed_labels.line_level:
            if not any(
                locus.program == ref.program
                and locus.file == ref.file
                and locus.line_span[0] <= ref.line <= locus.line_span[1]
                for locus in self.code_locus.loci
            ):
                raise ValueError("proposal line citation falls outside its code locus")
        return self


class CandidatePairProposal(BaseModel):
    """One unreviewed temporal proposal whose two sides share identical code."""

    model_config = ConfigDict(extra="forbid")

    pair_id: str = Field(pattern=r"^t6v2-candidate-\d{2}$")
    origin: Literal["new_pair_fixture"]
    period: Period
    code_input_path: str = Field(
        pattern=r"^data/benchmark/t6-v2/candidates/programs/T6V2P[345][A-Z0-9]+\.cbl$"
    )
    code_sha256: Sha256
    sides: tuple[CandidateSideProposal, CandidateSideProposal]
    review_state: Literal["candidate_unreviewed"]
    human_primary_review: None = None
    independent_verification: None = None
    adjudication: None = None
    eligible_for_evaluation: Literal[False] = False
    development_use_prohibited: Literal[True] = True

    @model_validator(mode="after")
    def _temporal_flip_is_only_a_proposal(self) -> CandidatePairProposal:
        expected_side_ids = {f"{self.pair_id}-a", f"{self.pair_id}-b"}
        if {side.candidate_side_id for side in self.sides} != expected_side_ids:
            raise ValueError("candidate side IDs must be bound to their pair ID")
        if self.sides[0].code_locus != self.sides[1].code_locus:
            raise ValueError(
                "candidate temporal sides must share an identical code locus"
            )
        axes = {
            (side.authority.version, side.authority.effective_date)
            for side in self.sides
        }
        if len(axes) != 2:
            raise ValueError("candidate temporal sides must use different versions")
        verdicts = {side.proposed_drift_type != "D7_conformant" for side in self.sides}
        if verdicts != {False, True}:
            raise ValueError("candidate proposal must contain a verdict flip")
        return self


class BlindedReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: None = None
    drift_type: None = None
    line_level: None = None
    rationale: None = None
    uncertainty_notes: None = None


class BlindedReviewItem(BaseModel):
    """One coordinator-held release envelope with no canonical source mapping."""

    model_config = ConfigDict(extra="forbid")

    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    authority: RegulationClause
    source_alias: str = Field(pattern=r"^src-[0-9a-f]{12}$")
    source_text: str = Field(min_length=20)
    release_ordinal: int = Field(ge=1, le=22)
    review_response: BlindedReviewResponse


class SequentialReleasePolicy(BaseModel):
    """Fail-closed attestation for the non-cryptographic offline blind."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    release_mode: Literal["sequential_one_item"]
    max_active_items: Literal[1]
    packet_role: Literal["coordinator_release_queue_not_distributable"]
    full_packet_distribution_prohibited: Literal[True]
    canonical_source_map_distribution_prohibited: Literal[True]
    prior_item_context_retention_prohibited: Literal[True]
    source_alias_scope: Literal["side_specific"]
    offline_pair_unlinkability: Literal["not_cryptographically_guaranteed"]
    compromised_diagnostics: list[ArtifactPin]


class PrimaryReviewIdentityProtocol(BaseModel):
    """Public, pre-release trust anchor for the human-primary review pass."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    protocol_id: str = Field(min_length=1)
    signature_algorithm: Literal["Ed25519"]
    signed_payload_domain: Literal["cobol-archaeologist/t6-primary-review/v1"]
    public_key_base64: str = Field(min_length=44, max_length=44)
    public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_key_repository_storage_prohibited: Literal[True]
    frozen_before_first_release: Literal[True]


class AIPrimaryReviewPolicy(BaseModel):
    """Frozen controls for the explicitly non-human primary review pass."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    review_role: Literal["ai_primary"]
    provider: Literal["chatgpt-codex"]
    authentication: Literal["ChatGPT"]
    model_id: Literal["gpt-5.6-sol"]
    reasoning_effort: Literal["max"]
    visible_review_items_per_call: Literal[1]
    staged_source_bundles_per_call: Literal[0]
    tools_authorized_per_call: Literal[0]
    prior_item_context_included: Literal[False]
    fresh_context_per_attempt: Literal[True]
    human_reviewer_claim_prohibited: Literal[True]
    independent_verifier_model_id: Literal["gpt-5.6-luna"]
    same_model_as_independent_verifier_prohibited: Literal[True]
    controlled_transport: Literal["collaboration_subagent"]
    coordinator_task_identity: Literal["/root/ai_primary_review_coordinator"]
    fork_turns: Literal["none"]
    prompt_and_final_message_bytes_pinned: Literal[True]
    native_execution_claim_prohibited: Literal[True]


class T6V2Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    lifecycle_state: Literal["candidate_preparation_only"]
    source_benchmark: ArtifactPin
    authority_manifest: ArtifactPin
    candidate_proposals: ArtifactPin
    blinded_review_packet: ArtifactPin
    blind_release_policy: ArtifactPin
    review_response_schema: ArtifactPin
    ai_primary_review_policy: ArtifactPin
    candidate_programs: list[CandidateProgramPin]
    authority_sources: list[AuthorityPin]
    inherited_review_evidence: list[ArtifactPin]
    reviewed_pair_count: Literal[9]
    candidate_pair_count: Literal[11]
    target_pair_count: Literal[20]
    evaluation_eligible_pair_count: Literal[9]
    evaluation_ready: Literal[False]
    development_use_prohibited: Literal[True]
    v1_excluded_candidate_ids: list[str]
    carried_forward_pairs: list[CarriedForwardPair]
    candidate_pair_specs: list[CandidatePairSpec]

    @model_validator(mode="after")
    def _freeze_invariants(self) -> T6V2Manifest:
        if len(self.carried_forward_pairs) != self.reviewed_pair_count:
            raise ValueError("reviewed_pair_count must equal carried pair references")
        if len(self.candidate_pair_specs) != self.candidate_pair_count:
            raise ValueError("candidate_pair_count must equal candidate specifications")
        if len(self.candidate_programs) != self.candidate_pair_count:
            raise ValueError("candidate_pair_count must equal candidate program pins")
        if (
            self.target_pair_count
            != self.reviewed_pair_count + self.candidate_pair_count
        ):
            raise ValueError("target count must equal reviewed plus candidate pairs")
        if self.evaluation_eligible_pair_count != len(self.carried_forward_pairs):
            raise ValueError("only reviewed carried pairs are evaluation eligible")

        pair_ids = [
            *(pair.pair_id for pair in self.carried_forward_pairs),
            *(pair.pair_id for pair in self.candidate_pair_specs),
        ]
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("T6-v2 pair IDs must be unique")
        if {pin.pair_id for pin in self.candidate_programs} != {
            pair.pair_id for pair in self.candidate_pair_specs
        }:
            raise ValueError("candidate program pins must cover the design roster")

        side_ids = [
            side.instance_id
            for pair in self.carried_forward_pairs
            for side in pair.sides
        ]
        if len(side_ids) != len(set(side_ids)):
            raise ValueError("a v1 row cannot be carried into more than one pair")
        if set(side_ids) & set(self.v1_excluded_candidate_ids):
            raise ValueError("v1 excluded candidates cannot be restored")

        distribution = Counter(pair.period for pair in self.candidate_pair_specs)
        if distribution != {"P3": 3, "P4": 4, "P5": 4}:
            raise ValueError("candidate design must freeze 3 P3, 4 P4, and 4 P5 pairs")
        return self


class T6V2ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carried_forward_pairs_validated: int
    candidate_specs_validated: int
    evaluation_eligible_pairs: int
    target_pairs: int
    evaluation_ready: bool
    review_gap_pairs: int
    candidate_fixture_pairs_validated: int = 0
    blinded_review_items_validated: int = 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_sha256_matches(path: Path, expected: str) -> bool:
    """Match text pins across Git's LF/CRLF checkout normalization."""

    data = path.read_bytes()
    candidates = {hashlib.sha256(data).hexdigest()}
    if path.suffix.lower() in {".cbl", ".cpy", ".json", ".jsonl", ".md", ".txt"}:
        lf_data = data.replace(b"\r\n", b"\n")
        candidates.add(hashlib.sha256(lf_data).hexdigest())
        candidates.add(
            hashlib.sha256(lf_data.replace(b"\n", b"\r\n")).hexdigest()
        )
    return expected in candidates


def _row_sha256(raw_line: str) -> str:
    return hashlib.sha256(raw_line.encode("utf-8")).hexdigest()


def _repo_path(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"artifact path escapes repository root: {relative}")
    return resolved


def load_t6_v2_manifest(path: Path) -> T6V2Manifest:
    return T6V2Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    rows: list[BaseModel] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            rows.append(model.model_validate_json(raw_line))
        except ValueError as exc:
            raise ValueError(f"invalid {path.name} line {line_number}: {exc}") from exc
    return rows


def load_candidate_pair_proposals(path: Path) -> list[CandidatePairProposal]:
    return [
        row
        for row in _load_jsonl(path, CandidatePairProposal)
        if isinstance(row, CandidatePairProposal)
    ]


def load_blinded_review_packet(path: Path) -> list[BlindedReviewItem]:
    return [
        row
        for row in _load_jsonl(path, BlindedReviewItem)
        if isinstance(row, BlindedReviewItem)
    ]


def load_sequential_release_policy(path: Path) -> SequentialReleasePolicy:
    return SequentialReleasePolicy.model_validate_json(path.read_text(encoding="utf-8"))


def validate_candidate_artifacts(
    *, root: Path, manifest: T6V2Manifest, proposal_path: Path, packet_path: Path
) -> tuple[int, int]:
    """Validate unreviewed fixtures and their label-blinded review projection."""

    proposals = load_candidate_pair_proposals(proposal_path)
    packet = load_blinded_review_packet(packet_path)
    if len(proposals) != manifest.candidate_pair_count:
        raise ValueError("candidate proposal count differs from frozen manifest")
    if len(packet) != 2 * manifest.candidate_pair_count:
        raise ValueError("blinded packet must contain two items per candidate pair")

    specs = {spec.pair_id: spec for spec in manifest.candidate_pair_specs}
    program_pins = {pin.pair_id: pin for pin in manifest.candidate_programs}
    if {pair.pair_id for pair in proposals} != set(specs):
        raise ValueError("candidate proposal IDs differ from frozen design roster")

    blind_projection: dict[str, dict[str, object]] = {}
    for pair in proposals:
        spec = specs[pair.pair_id]
        if Path(pair.code_input_path).name != spec.planned_code_input:
            raise ValueError(f"fixture path differs from design: {pair.pair_id}")
        program_pin = program_pins[pair.pair_id]
        if (
            pair.code_input_path != program_pin.path
            or pair.code_sha256 != program_pin.sha256
        ):
            raise ValueError(f"fixture differs from manifest pin: {pair.pair_id}")
        code_path = _repo_path(root, pair.code_input_path)
        if not code_path.is_file() or not artifact_sha256_matches(
            code_path, pair.code_sha256
        ):
            raise ValueError(f"candidate code pin changed: {pair.pair_id}")
        source_lines = code_path.read_text(encoding="utf-8").splitlines()

        expected_authorities = {
            spec.old_authority.source_role,
            spec.new_authority.source_role,
        }
        actual_authorities: set[str] = set()
        for side in pair.sides:
            expected_interprocedural = spec.locality == "interprocedural"
            if side.code_locus.is_interprocedural != expected_interprocedural:
                raise ValueError(
                    f"fixture locality differs from design: {pair.pair_id}"
                )
            matching = [
                authority
                for authority in (spec.old_authority, spec.new_authority)
                if authority.version == side.authority.version
                and authority.effective_date == str(side.authority.effective_date)
                and authority.clause_id == side.authority.clause_id
            ]
            if len(matching) != 1:
                raise ValueError(
                    f"proposal authority differs from design: {pair.pair_id}"
                )
            actual_authorities.add(matching[0].source_role)
            for locus in side.code_locus.loci:
                if locus.line_span[1] > len(source_lines):
                    raise ValueError(f"candidate locus exceeds source: {pair.pair_id}")
                if not any(
                    f"PROGRAM-ID. {locus.program}." in line for line in source_lines
                ):
                    raise ValueError(
                        f"candidate locus program missing from source: {locus.program}"
                    )
            blind_projection[side.blind_review_id] = {
                "authority": side.authority,
                "source_alias": "src-"
                + hashlib.sha256(
                    f"t6-v2-source-alias:{side.blind_review_id}".encode()
                ).hexdigest()[:12],
                "source_text": code_path.read_text(encoding="utf-8"),
            }
        if actual_authorities != expected_authorities:
            raise ValueError(f"proposal does not span both authorities: {pair.pair_id}")

    packet_ids = [item.review_item_id for item in packet]
    if len(packet_ids) != len(set(packet_ids)):
        raise ValueError("blinded review IDs must be unique")
    if set(packet_ids) != set(blind_projection):
        raise ValueError("blinded packet IDs differ from sealed proposal key")
    ordinals = [item.release_ordinal for item in packet]
    if sorted(ordinals) != list(range(1, len(packet) + 1)):
        raise ValueError("blinded packet release ordinals must be complete and unique")
    for item in packet:
        expected = blind_projection[item.review_item_id]
        if (
            item.authority != expected["authority"]
            or item.source_alias != expected["source_alias"]
            or item.source_text != expected["source_text"]
        ):
            raise ValueError(
                f"blinded packet projection changed: {item.review_item_id}"
            )

    return len(proposals), len(packet)


def _validate_pin(root: Path, pin: ArtifactPin) -> None:
    path = _repo_path(root, pin.path)
    if not path.is_file():
        raise ValueError(f"pinned artifact does not exist: {pin.path}")
    if not artifact_sha256_matches(path, pin.sha256):
        raise ValueError(f"pinned artifact hash changed: {pin.path}")


def validate_t6_v2(*, root: Path, manifest_path: Path) -> T6V2ValidationReport:
    """Validate preparation pins without promoting unreviewed candidates."""

    manifest = load_t6_v2_manifest(manifest_path)
    _validate_pin(root, manifest.source_benchmark)
    _validate_pin(root, manifest.authority_manifest)
    _validate_pin(root, manifest.candidate_proposals)
    _validate_pin(root, manifest.blinded_review_packet)
    _validate_pin(root, manifest.blind_release_policy)
    _validate_pin(root, manifest.review_response_schema)
    _validate_pin(root, manifest.ai_primary_review_policy)
    AIPrimaryReviewPolicy.model_validate_json(
        _repo_path(root, manifest.ai_primary_review_policy.path).read_text(
            encoding="utf-8"
        )
    )
    for program in manifest.candidate_programs:
        _validate_pin(root, program)
    for evidence in manifest.inherited_review_evidence:
        _validate_pin(root, evidence)

    release_policy = load_sequential_release_policy(
        _repo_path(root, manifest.blind_release_policy.path)
    )
    if release_policy.max_active_items != 1:
        raise ValueError("blind review must release exactly one active item")
    for diagnostic in release_policy.compromised_diagnostics:
        _validate_pin(root, diagnostic)

    authority_payload = json.loads(
        _repo_path(root, manifest.authority_manifest.path).read_text(encoding="utf-8")
    )
    authorities = {entry["doc_role"]: entry for entry in authority_payload["entries"]}
    pinned_roles = {pin.source_role for pin in manifest.authority_sources}
    for pin in manifest.authority_sources:
        source = authorities.get(pin.source_role)
        if source is None:
            raise ValueError(f"unknown authority source role: {pin.source_role}")
        if source["file"] != pin.file or source["sha256"] != pin.sha256:
            raise ValueError(
                f"authority pin differs from source manifest: {pin.source_role}"
            )

    split_path = _repo_path(root, manifest.source_benchmark.path)
    raw_by_id: dict[str, str] = {}
    row_by_id: dict[str, DriftInstance] = {}
    for raw_line in split_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        row = DriftInstance.model_validate_json(raw_line)
        raw_by_id[row.instance_id] = raw_line
        row_by_id[row.instance_id] = row

    for pair in manifest.carried_forward_pairs:
        rows: list[DriftInstance] = []
        for side in pair.sides:
            raw_line = raw_by_id.get(side.instance_id)
            row = row_by_id.get(side.instance_id)
            if raw_line is None or row is None:
                raise ValueError(
                    f"carried row missing from v1 test: {side.instance_id}"
                )
            if _row_sha256(raw_line) != side.row_sha256:
                raise ValueError(f"carried row hash changed: {side.instance_id}")
            if str(row.regulation_clause.effective_date) != side.effective_date:
                raise ValueError(f"effective date changed: {side.instance_id}")
            if row.regulation_clause.version != side.version:
                raise ValueError(f"version changed: {side.instance_id}")
            if row.drift_type != side.expected_drift_type:
                raise ValueError(f"drift type changed: {side.instance_id}")
            rows.append(row)

        if rows[0].code_locus != rows[1].code_locus:
            raise ValueError(
                f"carried pair no longer shares one code locus: {pair.pair_id}"
            )
        temporal_axes = {
            (row.regulation_clause.version, row.regulation_clause.effective_date)
            for row in rows
        }
        if len(temporal_axes) != 2:
            raise ValueError(f"carried pair does not span two versions: {pair.pair_id}")
        verdicts = {row.drift_type != "D7_conformant" for row in rows}
        if verdicts != {False, True}:
            raise ValueError(f"carried pair does not flip judgment: {pair.pair_id}")

        code_path = _repo_path(root, pair.code_input_path)
        expected_program = Path(pair.code_input_path).name
        if any(row.provenance.base_program != expected_program for row in rows):
            raise ValueError(f"carried pair code input changed: {pair.pair_id}")
        if not artifact_sha256_matches(code_path, pair.code_sha256):
            raise ValueError(f"carried code hash changed: {pair.pair_id}")

    for candidate in manifest.candidate_pair_specs:
        for authority in (candidate.old_authority, candidate.new_authority):
            if authority.source_role not in pinned_roles:
                raise ValueError(
                    f"candidate authority is not pinned: {authority.source_role}"
                )

    candidate_count, review_item_count = validate_candidate_artifacts(
        root=root,
        manifest=manifest,
        proposal_path=_repo_path(root, manifest.candidate_proposals.path),
        packet_path=_repo_path(root, manifest.blinded_review_packet.path),
    )

    return T6V2ValidationReport(
        carried_forward_pairs_validated=len(manifest.carried_forward_pairs),
        candidate_specs_validated=len(manifest.candidate_pair_specs),
        evaluation_eligible_pairs=manifest.evaluation_eligible_pair_count,
        target_pairs=manifest.target_pair_count,
        evaluation_ready=manifest.evaluation_ready,
        review_gap_pairs=manifest.candidate_pair_count,
        candidate_fixture_pairs_validated=candidate_count,
        blinded_review_items_validated=review_item_count,
    )
