from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cobol_archaeologist.migration.contracts import (
    AllowedSourceScope,
    BehaviorCheck,
    DetectorVisibleCandidate,
    FrozenSource,
    MigrationCandidate,
    MigrationCase,
    OracleCandidateSpec,
)
from cobol_archaeologist.migration.roster import (
    CANDIDATE_INSTANCE_IDS,
    OUTPUT_DIR,
    build_candidate_artifacts,
    load_canonical_roster,
)


def _jsonl(path: Path, model_type):
    return [
        model_type.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_committed_candidate_artifacts_are_deterministic() -> None:
    expected = build_candidate_artifacts()

    assert set(expected) == {
        "candidate-manifest.json",
        "candidate-roster.jsonl",
        "detector-visible-candidates.jsonl",
        "oracle-candidate-specs.jsonl",
    }
    for name, content in expected.items():
        assert (OUTPUT_DIR / name).read_text(encoding="utf-8") == content


def test_roster_is_balanced_but_explicitly_pending_and_ineligible() -> None:
    candidates = _jsonl(OUTPUT_DIR / "candidate-roster.jsonl", MigrationCandidate)

    assert len(candidates) == 12
    assert tuple(candidate.instance_id for candidate in candidates) == (
        CANDIDATE_INSTANCE_IDS
    )
    assert Counter(candidate.drift_type for candidate in candidates) == {
        "D1_stale_threshold": 2,
        "D2_missing_rule": 2,
        "D3_contradictory": 2,
        "D4_stale_reference_data": 2,
        "D5_boundary_error": 2,
        "D6_dead_code": 2,
    }
    assert Counter(candidate.stratum.value for candidate in candidates) == {
        "local": 6,
        "interprocedural": 6,
    }
    assert all(not candidate.eligible_for_evaluation for candidate in candidates)
    assert all(
        candidate.review_state == "human_review_pending" for candidate in candidates
    )
    assert all(
        candidate.independent_verification == "pending" for candidate in candidates
    )
    assert all(candidate.selected_before_config3_results for candidate in candidates)


def test_detector_visible_and_oracle_specs_are_separate() -> None:
    detector_path = OUTPUT_DIR / "detector-visible-candidates.jsonl"
    oracle_path = OUTPUT_DIR / "oracle-candidate-specs.jsonl"
    detector = _jsonl(detector_path, DetectorVisibleCandidate)
    oracle = _jsonl(oracle_path, OracleCandidateSpec)

    assert {row.case_id for row in detector} == {row.case_id for row in oracle}
    assert all(row.verified_finding is None for row in detector)
    assert all(not row.eligible_for_evaluation for row in oracle)

    detector_text = detector_path.read_text(encoding="utf-8").casefold()
    for forbidden in (
        "code_locus",
        "gold_rationale",
        "mutation",
        "oracle_prediction",
        "intended_behavior",
        "unaffected_regressions",
    ):
        assert forbidden not in detector_text
    oracle_text = oracle_path.read_text(encoding="utf-8")
    assert "oracle_prediction" in oracle_text
    assert "intended_behavior" in oracle_text
    assert "unaffected_regressions" in oracle_text


def test_manifest_pins_every_candidate_artifact_hash() -> None:
    manifest = json.loads(
        (OUTPUT_DIR / "candidate-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["state"] == "candidate_only_human_review_pending"
    assert manifest["eligible_for_evaluation"] is False
    assert manifest["case_count"] == 12
    assert manifest["distinct_source_bundle_count"] == 9
    assert sorted(
        len(case_ids) for case_ids in manifest["repeated_source_bundle_groups"].values()
    ) == [2, 2, 2]
    assert manifest["stratum_counts"] == {"interprocedural": 6, "local": 6}
    for name, evidence in manifest["files"].items():
        content = (OUTPUT_DIR / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == evidence["sha256"]
        assert evidence["rows"] == 12


def _reviewed_case(
    review_hash: str,
    *,
    review_protocol_hash: str,
    validation_protocol_hash: str = "d" * 64,
) -> MigrationCase:
    return MigrationCase(
        case_id="migration_demo",
        instance_id="drift_000001",
        drift_type="D1_stale_threshold",
        stratum="local",
        validation_capability="batch_executable",
        primary_program="DEMO",
        frozen_sources=(FrozenSource(path="DEMO.cbl", sha256="a" * 64),),
        allowed_source_scope=(
            AllowedSourceScope(path="DEMO.cbl", line_spans=((1, 1),)),
        ),
        intended_behavior=BehaviorCheck(check_id="fixed", description="fixed"),
        unaffected_regressions=(
            BehaviorCheck(check_id="stable", description="stable"),
        ),
        detector_input_ref="detector/demo.json",
        oracle_evidence_ref="oracle/demo.json",
        review_protocol_sha256=review_protocol_hash,
        validation_protocol_sha256=validation_protocol_hash,
        review_state="human_primary_reviewed_and_verified",
        review_evidence_sha256=review_hash,
        eligible_for_evaluation=True,
    )


def _write_json(root: Path, relative: str, payload: dict) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(raw)
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}


def _write_review_graph(
    root: Path,
    *,
    duplicate_reviewer: bool = False,
    invalid_signature: bool = False,
) -> tuple[bytes, dict[str, str]]:
    evidence_path = root / "source-evidence.txt"
    evidence_path.write_text("reviewed source and behavior evidence", encoding="utf-8")
    source_pin = {
        "path": "source-evidence.txt",
        "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
    }
    response_pins: dict[str, dict[str, str]] = {}
    verification_pins: dict[str, dict[str, str]] = {}
    public_keys: dict[str, str] = {}
    private_keys: dict[str, Ed25519PrivateKey] = {}
    roles = (
        ("human_primary", "primary-a"),
        (
            "independent_verifier",
            "primary-a" if duplicate_reviewer else "verifier-b",
        ),
        ("adjudicator", "adjudicator-c"),
    )
    for index, (role, reviewer) in enumerate(roles, start=1):
        response_pin = _write_json(
            root,
            f"responses/{role}.json",
            {
                "schema_version": "migration-review-response-v1",
                "case_id": "migration_demo",
                "instance_id": "drift_000001",
                "review_role": role,
                "reviewer_identity": reviewer,
                "completed_at": "2026-08-24T10:00:00Z",
                "decision": "include",
                "rationale": f"{role} independently reviewed the case.",
                "evidence": [source_pin],
            },
        )
        response_pins[role] = response_pin
        private_key = private_keys.setdefault(
            reviewer,
            Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32),
        )
        public_keys[reviewer] = private_key.public_key().public_bytes_raw().hex()
        verification = {
            "schema_version": "migration-reviewer-verification-v1",
            "review_role": role,
            "reviewer_identity": reviewer,
            "response": response_pin,
            "identity_verified": True,
            "human_reviewer_verified": True,
            "verified_by_external_party": "external-review-office",
            "verification_method": "signed reviewer roster",
            "evidence_reference": f"registry:{reviewer}",
            "verified_at": "2026-08-24T11:00:00Z",
        }
        signed = json.dumps(
            verification, sort_keys=True, separators=(",", ":")
        ).encode()
        verification["signature_ed25519"] = private_key.sign(signed).hex()
        if invalid_signature and role == "human_primary":
            verification["signature_ed25519"] = "0" * 128
        verification_pins[role] = _write_json(
            root,
            f"identity/{role}.json",
            verification,
        )
    manifest = {
        "schema_version": "migration-review-evidence-v1",
        "case_id": "migration_demo",
        "instance_id": "drift_000001",
        "human_primary_response": response_pins["human_primary"],
        "independent_verifier_response": response_pins["independent_verifier"],
        "adjudication_response": response_pins["adjudicator"],
        "human_primary_identity_verification": verification_pins["human_primary"],
        "independent_verifier_identity_verification": verification_pins[
            "independent_verifier"
        ],
        "adjudicator_identity_verification": verification_pins["adjudicator"],
        "review_state": "human_primary_reviewed_and_verified",
        "eligible_for_evaluation": True,
    }
    return (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
        public_keys,
    )


def _write_review_protocol(
    root: Path,
    public_keys: dict[str, str],
    *,
    duplicate_reviewer: bool = False,
) -> str:
    roles = (
        ("human_primary", "primary-a"),
        (
            "independent_verifier",
            "primary-a" if duplicate_reviewer else "verifier-b",
        ),
        ("adjudicator", "adjudicator-c"),
    )
    raw = json.dumps(
        {
            "schema_version": "migration-review-protocol-v1",
            "state": "ready",
            "frozen_before_responses": True,
            "frozen_at": "2026-08-24T09:00:00Z",
            "runtime_source_sha256": "2" * 64,
            "reviewer_keys": [
                {
                    "review_role": role,
                    "reviewer_identity": reviewer,
                    "key_id": f"{role}-key",
                    "public_key_ed25519": public_keys[reviewer],
                }
                for role, reviewer in roles
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (root / "review-protocol.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_canonical_roster_resolves_and_hash_validates_external_review(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "reviews"
    evidence_root.mkdir()
    evidence, public_keys = _write_review_graph(evidence_root)
    protocol_hash = _write_review_protocol(evidence_root, public_keys)
    evidence_path = evidence_root / "migration_demo.json"
    evidence_path.write_bytes(evidence)
    case = _reviewed_case(
        hashlib.sha256(evidence).hexdigest(),
        review_protocol_hash=protocol_hash,
    )
    roster_path = tmp_path / "cases.jsonl"
    roster_path.write_text(case.model_dump_json() + "\n", encoding="utf-8")

    roster = load_canonical_roster(
        roster_path,
        review_evidence_root=evidence_root,
        protocol_root=evidence_root,
    )

    assert roster.cases == (case,)
    assert roster.review_evidence_sha256[case.case_id] == case.review_evidence_sha256
    evidence_path.write_bytes(evidence + b"\n")
    with pytest.raises(ValueError, match="review evidence hash mismatch"):
        load_canonical_roster(
            roster_path,
            review_evidence_root=evidence_root,
            protocol_root=evidence_root,
        )


def test_self_authored_review_literals_cannot_create_eligibility(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "reviews"
    evidence_root.mkdir()
    evidence = json.dumps(
        {
            "schema_version": "migration-review-evidence-v1",
            "case_id": "migration_demo",
            "instance_id": "drift_000001",
            "review_state": "human_primary_reviewed_and_verified",
            "eligible_for_evaluation": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (evidence_root / "migration_demo.json").write_bytes(evidence)
    protocol_hash = _write_review_protocol(
        evidence_root,
        {
            identity: Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)
            .public_key()
            .public_bytes_raw()
            .hex()
            for index, identity in enumerate(
                ("primary-a", "verifier-b", "adjudicator-c"), start=1
            )
        },
    )
    case = _reviewed_case(
        hashlib.sha256(evidence).hexdigest(),
        review_protocol_hash=protocol_hash,
    )
    roster_path = tmp_path / "cases.jsonl"
    roster_path.write_text(case.model_dump_json() + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="human_primary_response"):
        load_canonical_roster(
            roster_path,
            review_evidence_root=evidence_root,
            protocol_root=evidence_root,
        )


def test_primary_and_verifier_must_have_distinct_verified_identities(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "reviews"
    evidence_root.mkdir()
    evidence, public_keys = _write_review_graph(
        evidence_root, duplicate_reviewer=True
    )
    protocol_hash = _write_review_protocol(
        evidence_root, public_keys, duplicate_reviewer=True
    )
    (evidence_root / "migration_demo.json").write_bytes(evidence)
    case = _reviewed_case(
        hashlib.sha256(evidence).hexdigest(),
        review_protocol_hash=protocol_hash,
    )
    roster_path = tmp_path / "cases.jsonl"
    roster_path.write_text(case.model_dump_json() + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be distinct|identities.*distinct"):
        load_canonical_roster(
            roster_path,
            review_evidence_root=evidence_root,
            protocol_root=evidence_root,
        )


def test_unsigned_or_forged_reviewer_attestation_is_rejected(tmp_path: Path) -> None:
    evidence_root = tmp_path / "reviews"
    evidence_root.mkdir()
    evidence, public_keys = _write_review_graph(
        evidence_root, invalid_signature=True
    )
    protocol_hash = _write_review_protocol(evidence_root, public_keys)
    (evidence_root / "migration_demo.json").write_bytes(evidence)
    case = _reviewed_case(
        hashlib.sha256(evidence).hexdigest(),
        review_protocol_hash=protocol_hash,
    )
    roster_path = tmp_path / "cases.jsonl"
    roster_path.write_text(case.model_dump_json() + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid Ed25519 signature"):
        load_canonical_roster(
            roster_path,
            review_evidence_root=evidence_root,
            protocol_root=evidence_root,
        )
