from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from tree_sitter import Parser

from cobol_archaeologist.benchmark.t6_v2 import (
    CandidatePairProposal,
    T6V2Manifest,
    load_blinded_review_packet,
    load_candidate_pair_proposals,
    load_sequential_release_policy,
    load_t6_v2_manifest,
    validate_t6_v2,
)
from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.parser._grammar import get_language

ROOT = Path(__file__).resolve().parents[1]
T6_V2 = ROOT / "data" / "benchmark" / "t6-v2"


def test_t6_v2_preparation_manifest_is_fail_closed() -> None:
    manifest = load_t6_v2_manifest(T6_V2 / "manifest.json")

    assert manifest.lifecycle_state == "candidate_preparation_only"
    assert manifest.reviewed_pair_count == 9
    assert manifest.candidate_pair_count == 11
    assert manifest.target_pair_count == 20
    assert manifest.evaluation_eligible_pair_count == 9
    assert manifest.evaluation_ready is False
    assert manifest.development_use_prohibited is True

    assert len(manifest.carried_forward_pairs) == 9
    assert len(manifest.candidate_pair_specs) == 11
    assert {pair.period for pair in manifest.carried_forward_pairs} == {"P4", "P5"}
    assert [pair.period for pair in manifest.candidate_pair_specs].count("P3") == 3
    assert [pair.period for pair in manifest.candidate_pair_specs].count("P4") == 4
    assert [pair.period for pair in manifest.candidate_pair_specs].count("P5") == 4

    for candidate in manifest.candidate_pair_specs:
        assert candidate.review_state == "candidate_unreviewed"
        assert candidate.human_primary_review is None
        assert candidate.independent_verification is None
        assert candidate.adjudication is None
        assert candidate.eligible_for_evaluation is False
        assert candidate.development_use_prohibited is True


def test_t6_v2_carried_pairs_are_immutable_valid_v1_references() -> None:
    report = validate_t6_v2(root=ROOT, manifest_path=T6_V2 / "manifest.json")

    assert report.carried_forward_pairs_validated == 9
    assert report.candidate_specs_validated == 11
    assert report.evaluation_eligible_pairs == 9
    assert report.target_pairs == 20
    assert report.evaluation_ready is False
    assert report.review_gap_pairs == 11
    assert report.candidate_fixture_pairs_validated == 11
    assert report.blinded_review_items_validated == 22


def test_t6_v2_candidates_cannot_claim_review_or_evaluation_eligibility() -> None:
    payload = json.loads((T6_V2 / "manifest.json").read_text(encoding="utf-8"))
    candidate = payload["candidate_pair_specs"][0]
    candidate["review_state"] = "independently_verified"
    candidate["human_primary_review"] = {"reviewer": "invented"}
    candidate["eligible_for_evaluation"] = True

    with pytest.raises(ValidationError):
        T6V2Manifest.model_validate(payload)


def test_t6_v2_schema_marks_candidate_review_fields_as_null_only() -> None:
    schema = json.loads((T6_V2 / "schema.json").read_text(encoding="utf-8"))
    candidate = schema["$defs"]["CandidatePairSpec"]

    assert schema["$id"].endswith("/t6-v2/schema.json")
    assert candidate["properties"]["human_primary_review"]["type"] == "null"
    assert candidate["properties"]["independent_verification"]["type"] == "null"
    assert candidate["properties"]["adjudication"]["type"] == "null"
    assert candidate["properties"]["eligible_for_evaluation"]["const"] is False


def test_t6_v2_does_not_restore_v1_exclusions() -> None:
    manifest = load_t6_v2_manifest(T6_V2 / "manifest.json")
    carried_ids = {
        side.instance_id
        for pair in manifest.carried_forward_pairs
        for side in pair.sides
    }

    assert carried_ids.isdisjoint(manifest.v1_excluded_candidate_ids)
    assert all(
        candidate.origin == "new_pair_design"
        for candidate in manifest.candidate_pair_specs
    )


def test_candidate_fixtures_have_two_temporal_sides_and_one_code_locus() -> None:
    proposals = load_candidate_pair_proposals(
        T6_V2 / "candidates" / "pair_proposals.jsonl"
    )

    assert len(proposals) == 11
    assert [pair.period for pair in proposals].count("P3") == 3
    assert [pair.period for pair in proposals].count("P4") == 4
    assert [pair.period for pair in proposals].count("P5") == 4
    assert sum(pair.sides[0].code_locus.is_interprocedural for pair in proposals) == 3
    for pair in proposals:
        left, right = pair.sides
        assert left.code_locus == right.code_locus
        assert left.authority.version != right.authority.version
        assert {
            left.proposed_drift_type == "D7_conformant",
            right.proposed_drift_type == "D7_conformant",
        } == {False, True}
        assert pair.review_state == "candidate_unreviewed"
        assert pair.eligible_for_evaluation is False
        assert pair.development_use_prohibited is True


def test_blinded_packet_is_an_opaque_sequential_release_queue() -> None:
    proposal_path = T6_V2 / "candidates" / "pair_proposals.jsonl"
    packet_path = T6_V2 / "review" / "packet.jsonl"
    proposals = load_candidate_pair_proposals(proposal_path)
    packet = load_blinded_review_packet(packet_path)

    sealed_order = [side.blind_review_id for pair in proposals for side in pair.sides]
    packet_order = [item.review_item_id for item in packet]
    assert len(packet_order) == 22
    assert set(packet_order) == set(sealed_order)
    assert packet_order != sealed_order

    raw_packet = packet_path.read_text(encoding="utf-8")
    for forbidden in (
        '"pair_id"',
        '"candidate_side_id"',
        '"proposed_drift_type"',
        '"proposal_rationale"',
        '"review_state"',
        '"eligible_for_evaluation"',
        '"code_input_path"',
        '"code_sha256"',
        '"code_locus"',
        '"line_span"',
    ):
        assert forbidden not in raw_packet
    assert [item.release_ordinal for item in packet] == list(range(1, 23))
    assert len({item.source_alias for item in packet}) == 22
    for item in packet:
        assert item.source_alias.startswith("src-")
        assert "PROGRAM-ID." in item.source_text
        assert item.review_response.decision is None
        assert item.review_response.drift_type is None
        assert item.review_response.line_level is None
        assert item.review_response.rationale is None
        assert item.review_response.uncertainty_notes is None

    policy = load_sequential_release_policy(T6_V2 / "review/release-policy.json")
    assert policy.release_mode == "sequential_one_item"
    assert policy.max_active_items == 1
    assert policy.full_packet_distribution_prohibited
    assert policy.canonical_source_map_distribution_prohibited
    assert policy.prior_item_context_retention_prohibited
    assert policy.offline_pair_unlinkability == "not_cryptographically_guaranteed"


def test_candidate_proposal_rejects_mismatched_locus_or_non_flip() -> None:
    payload = json.loads(
        (T6_V2 / "candidates" / "pair_proposals.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    payload["sides"][1]["code_locus"]["loci"][0]["line_span"] = [21, 37]
    with pytest.raises(ValidationError, match="identical code locus"):
        CandidatePairProposal.model_validate(payload)

    payload = json.loads(
        (T6_V2 / "candidates" / "pair_proposals.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    payload["sides"][1]["proposed_drift_type"] = "D7_conformant"
    payload["sides"][1]["proposed_labels"] = {
        "program_level": "conformant",
        "paragraph_level": "conformant",
        "line_level": [],
    }
    with pytest.raises(ValidationError, match="verdict flip"):
        CandidatePairProposal.model_validate(payload)


def test_candidate_cobol_fixtures_parse_without_error_nodes() -> None:
    parser = Parser()
    parser.set_language(get_language())

    def error_count(node: object) -> int:
        children = getattr(node, "children", [])
        return int(getattr(node, "type", None) == "ERROR") + sum(
            error_count(child) for child in children
        )

    programs = sorted((T6_V2 / "candidates" / "programs").glob("*.cbl"))
    assert len(programs) == 11
    for program in programs:
        source = preprocess(program.read_text(encoding="utf-8")).text
        assert error_count(parser.parse(source.encode()).root_node) == 0, program.name
