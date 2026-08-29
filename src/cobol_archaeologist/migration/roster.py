"""Deterministic builder for the candidate-only T6 migration roster."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.migration.contracts import (
    AllowedSourceScope,
    BehaviorCheck,
    CanonicalReviewEvidence,
    CaseStratum,
    DetectorVisibleCandidate,
    ExternalReviewerVerification,
    FrozenSource,
    MigrationCandidate,
    MigrationCase,
    MigrationEvidencePin,
    MigrationReviewProtocol,
    MigrationReviewResponse,
    OracleCandidateSpec,
    ValidationCapability,
)
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_TEST = ROOT / "data" / "benchmark" / "v1" / "test.jsonl"
OUTPUT_DIR = ROOT / "data" / "migration"

# Selected from the frozen v1 test inventory before configuration-3 results.
# Two candidates per D1-D6; D1/D3/D6 provide six interprocedural cases and
# D2/D4/D5 provide six local cases.
CANDIDATE_INSTANCE_IDS = (
    "drift_075075",
    "drift_255807",
    "drift_000018",
    "drift_247749",
    "drift_106241",
    "drift_548537",
    "drift_191889",
    "drift_366948",
    "drift_345332",
    "drift_479846",
    "drift_052199",
    "drift_071627",
)


@dataclass(frozen=True)
class LoadedCanonicalRoster:
    """A canonical roster whose external review evidence has been verified."""

    cases: tuple[MigrationCase, ...]
    roster_sha256: str
    review_evidence_sha256: dict[str, str]


def _pinned_bytes(
    root: Path,
    pin: MigrationEvidencePin,
    *,
    context: str,
) -> bytes:
    path = (root / pin.path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{context} escapes the review evidence root") from exc
    raw = path.read_bytes()
    observed = _sha256(raw)
    if observed != pin.sha256:
        raise ValueError(
            f"{context} hash mismatch: expected {pin.sha256}, observed {observed}"
        )
    return raw


def _validated_review_role(
    *,
    root: Path,
    case: MigrationCase,
    role: str,
    response_pin: MigrationEvidencePin,
    verification_pin: MigrationEvidencePin,
    review_protocol: MigrationReviewProtocol,
) -> MigrationReviewResponse:
    response = MigrationReviewResponse.model_validate_json(
        _pinned_bytes(root, response_pin, context=f"{role} response")
    )
    if (
        response.case_id != case.case_id
        or response.instance_id != case.instance_id
        or response.review_role != role
    ):
        raise ValueError(f"{role} response identity mismatch for {case.case_id}")
    for index, evidence_pin in enumerate(response.evidence):
        _pinned_bytes(
            root,
            evidence_pin,
            context=f"{role} response evidence {index}",
        )
    verification = ExternalReviewerVerification.model_validate_json(
        _pinned_bytes(
            root,
            verification_pin,
            context=f"{role} external identity verification",
        )
    )
    if (
        verification.review_role != role
        or verification.reviewer_identity != response.reviewer_identity
        or verification.response != response_pin
    ):
        raise ValueError(
            f"{role} external verification does not pin the reviewed response"
        )
    matching_keys = [
        key
        for key in review_protocol.reviewer_keys
        if key.review_role == role
        and key.reviewer_identity == response.reviewer_identity
    ]
    if len(matching_keys) != 1:
        raise ValueError(
            f"{role} response does not match its pre-review protocol key"
        )
    if response.completed_at <= review_protocol.frozen_at:
        raise ValueError(f"{role} response predates the frozen review protocol")
    if verification.verified_at <= review_protocol.frozen_at:
        raise ValueError(f"{role} verification predates the frozen review protocol")
    public_key_hex = matching_keys[0].public_key_ed25519
    signed = json.dumps(
        verification.model_dump(mode="json", exclude={"signature_ed25519"}),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(
            bytes.fromhex(verification.signature_ed25519),
            signed,
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError(
            f"{role} external verification has an invalid Ed25519 signature"
        ) from exc
    return response


def load_canonical_roster(
    roster_path: Path,
    *,
    review_evidence_root: Path,
    protocol_root: Path,
) -> LoadedCanonicalRoster:
    """Load reviewed cases and verify every referenced eligibility artifact.

    Review evidence is deliberately external to the roster.  The normalized
    reference, exact bytes, case identity, and reviewed/eligible state must all
    agree before a case can enter a migration denominator.
    """

    roster_path = Path(roster_path)
    roster_bytes = roster_path.read_bytes()
    cases = tuple(
        MigrationCase.model_validate_json(line)
        for line in roster_bytes.decode("utf-8").splitlines()
        if line.strip()
    )
    if not cases:
        raise ValueError("canonical migration roster cannot be empty")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("canonical migration roster case IDs must be unique")
    instance_ids = [case.instance_id for case in cases]
    if len(instance_ids) != len(set(instance_ids)):
        raise ValueError("canonical migration roster instance IDs must be unique")
    evidence_root = Path(review_evidence_root).resolve()
    protocol_root = Path(protocol_root).resolve()
    review_protocol_path = (protocol_root / "review-protocol.json").resolve()
    try:
        review_protocol_path.relative_to(protocol_root)
    except ValueError as exc:
        raise ValueError("review protocol escapes its canonical root") from exc
    review_protocol_bytes = review_protocol_path.read_bytes()
    review_protocol_sha256 = _sha256(review_protocol_bytes)
    review_protocol = MigrationReviewProtocol.model_validate_json(
        review_protocol_bytes
    )
    verified_hashes: dict[str, str] = {}
    for case in cases:
        if case.review_protocol_sha256 != review_protocol_sha256:
            raise ValueError(
                f"review protocol hash mismatch for {case.case_id}"
            )
        evidence_path = (evidence_root / f"{case.case_id}.json").resolve()
        try:
            evidence_path.relative_to(evidence_root)
        except ValueError as exc:
            raise ValueError(
                f"review evidence escapes its root for {case.case_id}"
            ) from exc
        evidence_bytes = evidence_path.read_bytes()
        observed_hash = _sha256(evidence_bytes)
        if observed_hash != case.review_evidence_sha256:
            raise ValueError(
                f"review evidence hash mismatch for {case.case_id}: expected "
                f"{case.review_evidence_sha256}, observed {observed_hash}"
            )
        evidence = CanonicalReviewEvidence.model_validate_json(evidence_bytes)
        if evidence.case_id != case.case_id or evidence.instance_id != case.instance_id:
            raise ValueError(
                f"review evidence identity mismatch for {case.case_id}"
            )
        if evidence.review_state != case.review_state:
            raise ValueError(f"review evidence state mismatch for {case.case_id}")
        primary = _validated_review_role(
            root=evidence_root,
            case=case,
            role="human_primary",
            response_pin=evidence.human_primary_response,
            verification_pin=evidence.human_primary_identity_verification,
            review_protocol=review_protocol,
        )
        verifier = _validated_review_role(
            root=evidence_root,
            case=case,
            role="independent_verifier",
            response_pin=evidence.independent_verifier_response,
            verification_pin=evidence.independent_verifier_identity_verification,
            review_protocol=review_protocol,
        )
        adjudicator = _validated_review_role(
            root=evidence_root,
            case=case,
            role="adjudicator",
            response_pin=evidence.adjudication_response,
            verification_pin=evidence.adjudicator_identity_verification,
            review_protocol=review_protocol,
        )
        reviewer_identities = {
            primary.reviewer_identity,
            verifier.reviewer_identity,
            adjudicator.reviewer_identity,
        }
        if len(reviewer_identities) != 3:
            raise ValueError(
                f"primary, verifier, and adjudicator must be distinct for {case.case_id}"
            )
        verified_hashes[case.case_id] = observed_hash

    return LoadedCanonicalRoster(
        cases=cases,
        roster_sha256=_sha256(roster_bytes),
        review_evidence_sha256=verified_hashes,
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_hash(model) -> str:
    payload = json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return _sha256(payload)


def _read_rows(path: Path) -> dict[str, DriftInstance]:
    rows: dict[str, DriftInstance] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = DriftInstance.model_validate_json(line)
        rows[row.instance_id] = row
    return rows


def _locus_path(row: DriftInstance, program: str, file: str | None) -> str:
    if file:
        return Path(file).name
    main = Path(row.provenance.base_program)
    if Path(program).stem.upper() == main.stem.upper():
        return main.name
    return program if Path(program).suffix else f"{program}.cbl"


def _allowed_scope(row: DriftInstance) -> tuple[AllowedSourceScope, ...]:
    spans: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for locus in row.code_locus.loci:
        spans[_locus_path(row, locus.program, locus.file)].append(locus.line_span)
    return tuple(
        AllowedSourceScope(path=path, line_spans=tuple(sorted(values)))
        for path, values in sorted(spans.items())
    )


def _capability(row: DriftInstance) -> ValidationCapability:
    if any(
        (locus.file or "").lower().endswith(".cpy") for locus in row.code_locus.loci
    ):
        return ValidationCapability.COPYBOOK_FANOUT
    return ValidationCapability.BATCH_EXECUTABLE


def _behavior_specs(
    row: DriftInstance,
) -> tuple[BehaviorCheck, tuple[BehaviorCheck, ...]]:
    clause = row.regulation_clause
    intended = BehaviorCheck(
        check_id="intended-regulatory-behavior",
        description=(
            f"The remediated case satisfies {clause.doc} clause {clause.clause_id}: "
            f"{clause.text}"
        ),
    )
    class_specific = {
        "D1_stale_threshold": (
            "All decisions below and above the corrected threshold, and every "
            "untargeted composite-clause leaf, retain their prior behavior."
        ),
        "D2_missing_rule": (
            "Existing valid classification and validation outcomes outside the "
            "newly restored mandatory rule remain unchanged."
        ),
        "D3_contradictory": (
            "Non-conflicting acceptance and rejection paths retain their prior "
            "outcomes after the contradictory branch is repaired."
        ),
        "D4_stale_reference_data": (
            "Every unchanged registry member retains its prior accepted or "
            "rejected outcome across all affected hosts."
        ),
        "D5_boundary_error": (
            "Values strictly below and strictly above the corrected boundary "
            "retain their prior outcomes; only the exact boundary changes."
        ),
        "D6_dead_code": (
            "Unrelated batch output and downstream control flow remain unchanged "
            "when the regulatory path becomes reachable again."
        ),
    }[row.drift_type]
    regressions = (
        BehaviorCheck(
            check_id="unaffected-outside-locus",
            description=(
                "Behavior outside the candidate's allowlisted source loci remains "
                "unchanged under the frozen regression fixtures."
            ),
        ),
        BehaviorCheck(check_id="class-specific-regression", description=class_specific),
    )
    return intended, regressions


def build_candidate_artifacts(
    benchmark_path: Path = BENCHMARK_TEST,
) -> dict[str, str]:
    """Return deterministic artifact contents without claiming review completion."""

    inventory_bytes = benchmark_path.read_bytes()
    inventory_hash = _sha256(inventory_bytes)
    rows = _read_rows(benchmark_path)
    missing = set(CANDIDATE_INSTANCE_IDS) - set(rows)
    if missing:
        raise ValueError(
            f"candidate IDs missing from benchmark inventory: {sorted(missing)}"
        )

    candidates: list[MigrationCandidate] = []
    detector_rows: list[DetectorVisibleCandidate] = []
    oracle_rows: list[OracleCandidateSpec] = []
    for instance_id in CANDIDATE_INSTANCE_IDS:
        row = rows[instance_id]
        source = materialize(row)
        case_id = f"migration_{instance_id.removeprefix('drift_')}"
        frozen_sources = tuple(
            FrozenSource(path=name, sha256=_sha256(content.encode()))
            for name, content in sorted(source.files.items())
        )
        capability = _capability(row)
        affected_hosts = (
            tuple(sorted({locus.program for locus in row.code_locus.loci}))
            if capability == ValidationCapability.COPYBOOK_FANOUT
            else ()
        )
        intended, regressions = _behavior_specs(row)
        candidate = MigrationCandidate(
            case_id=case_id,
            instance_id=instance_id,
            drift_type=row.drift_type,
            stratum=(
                CaseStratum.INTERPROCEDURAL
                if row.code_locus.is_interprocedural
                else CaseStratum.LOCAL
            ),
            validation_capability=capability,
            primary_program=source.main_file,
            source_bundle_sha256=source.source_sha256,
            frozen_sources=frozen_sources,
            benchmark_row_sha256=_canonical_hash(row),
            benchmark_inventory_sha256=inventory_hash,
            detector_visible_ref=(
                f"data/migration/detector-visible-candidates.jsonl#{case_id}"
            ),
            oracle_spec_ref=f"data/migration/oracle-candidate-specs.jsonl#{case_id}",
            selection_rationale=(
                "Candidate-only pre-result selection: balances two rows per D1-D6 "
                "and contributes to the six-local/six-interprocedural roster. "
                "Human primary review and independent verification remain pending."
            ),
        )
        candidates.append(candidate)
        detector_rows.append(
            DetectorVisibleCandidate(
                case_id=case_id,
                instance_id=instance_id,
                regulation_clause=row.regulation_clause,
                primary_program=source.main_file,
                source_bundle_sha256=source.source_sha256,
                frozen_sources=frozen_sources,
            )
        )
        oracle_rows.append(
            OracleCandidateSpec(
                case_id=case_id,
                instance_id=instance_id,
                oracle_prediction=DriftPrediction.from_gold(row),
                allowed_source_scope=_allowed_scope(row),
                intended_behavior=intended,
                unaffected_regressions=regressions,
                affected_hosts=affected_hosts,
            )
        )

    def jsonl(models: list) -> str:
        return "".join(
            json.dumps(model.model_dump(mode="json"), sort_keys=True) + "\n"
            for model in models
        )

    payloads = {
        "candidate-roster.jsonl": jsonl(candidates),
        "detector-visible-candidates.jsonl": jsonl(detector_rows),
        "oracle-candidate-specs.jsonl": jsonl(oracle_rows),
    }
    drift_counts = Counter(candidate.drift_type for candidate in candidates)
    stratum_counts = Counter(candidate.stratum.value for candidate in candidates)
    capability_counts = Counter(
        candidate.validation_capability.value for candidate in candidates
    )
    source_groups: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        source_groups[candidate.source_bundle_sha256].append(candidate.case_id)
    repeated_sources = {
        digest: case_ids
        for digest, case_ids in sorted(source_groups.items())
        if len(case_ids) > 1
    }
    manifest = {
        "schema_version": "migration-candidate-manifest-v1",
        "state": "candidate_only_human_review_pending",
        "eligible_for_evaluation": False,
        "selected_before_config3_results": True,
        "selection_date": "2026-08-24",
        "benchmark_inventory": "data/benchmark/v1/test.jsonl",
        "benchmark_inventory_sha256": inventory_hash,
        "case_count": len(candidates),
        "distinct_source_bundle_count": len(source_groups),
        "repeated_source_bundle_groups": repeated_sources,
        "drift_type_counts": dict(sorted(drift_counts.items())),
        "stratum_counts": dict(sorted(stratum_counts.items())),
        "validation_capability_counts": dict(sorted(capability_counts.items())),
        "cics_candidates_available_in_frozen_test_inventory": 0,
        "notes": [
            "This is not data/migration/cases.jsonl and cannot authorize T6.2.",
            "Human-primary review, independent verification, and adjudication are pending.",
            "Detector-visible envelopes contain no oracle loci, labels, rationale, or behavior specs.",
            "Oracle and intended/unaffected behavior specifications are separated for review.",
            "No model outputs, patches, validation outcomes, or migration success claims are present.",
            "Repeated materialized source bundles are disclosed and must be resolved or justified before canonical promotion.",
        ],
        "files": {
            name: {"sha256": _sha256(content.encode()), "rows": len(candidates)}
            for name, content in sorted(payloads.items())
        },
    }
    payloads["candidate-manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return payloads


def write_candidate_artifacts(output_dir: Path = OUTPUT_DIR) -> None:
    """Mechanically materialize the deterministic candidate-only artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in build_candidate_artifacts().items():
        (output_dir / name).write_text(content, encoding="utf-8", newline="\n")
