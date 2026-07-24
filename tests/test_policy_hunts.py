"""T3.6 gates: registered D1-D7 policy hunts over cached investigations."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.agent.policy import (
    HUNT_REGISTRY,
    HuntOutcome,
    get_hunt,
)
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.model import verify as verify_module
from cobol_archaeologist.model.prompt import HUNT_PROMPTS, CachedDecisionModel
from cobol_archaeologist.model.verify import LexicalEntailer, VerificationTier
from cobol_archaeologist.schemas import DriftInstance, RegulationClause, resolve_path

FIX = Path(__file__).resolve().parent / "fixtures" / "hunts"
CACHE = FIX / "cached_decisions.json"
CORPUS = FIX / "corpus"
POSITIVE_CASES = {
    "D1_stale_threshold": "d1",
    "D2_missing_rule": "d2",
    "D3_contradictory": "d3",
    "D4_stale_reference_data": "d4",
    "D5_boundary_error": "d5",
    "D6_dead_code": "d6",
    "D7_conformant": "d7",
}


@pytest.fixture()
def tools() -> StubToolLayer:
    return StubToolLayer(CORPUS)


def _rows(case: str) -> list[dict]:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    return raw[case]


def _clause(case: str) -> RegulationClause:
    final = next(row for row in reversed(_rows(case)) if row["kind"] == "finding")
    return RegulationClause.model_validate(final["prediction"]["regulation_clause"])


def _run(
    tools: StubToolLayer,
    drift_type: str,
    case: str,
) -> HuntOutcome:
    return get_hunt(drift_type).run(
        clause=_clause(case) if any(r["kind"] == "finding" for r in _rows(case))
        else RegulationClause.model_validate(
            json.loads((CORPUS / "clauses.jsonl").read_text(encoding="utf-8").splitlines()[0])
        ),
        tools=tools,
        model=CachedDecisionModel(CACHE, cache_key=case),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )


def test_registry_has_exactly_one_hunt_per_drift_class():
    assert set(HUNT_REGISTRY) == set(POSITIVE_CASES)
    assert set(HUNT_PROMPTS) == set(POSITIVE_CASES)
    assert all(hunt.drift_type == key for key, hunt in HUNT_REGISTRY.items())


@pytest.mark.parametrize(("drift_type", "case"), POSITIVE_CASES.items())
def test_each_hunt_emits_schema_valid_verified_finding(tools, drift_type, case):
    outcome = _run(tools, drift_type, case)
    assert isinstance(outcome, HuntOutcome)
    assert not outcome.abstained
    assert isinstance(outcome.finding, DriftInstance)
    assert outcome.finding.drift_type == drift_type
    assert outcome.verification is not None and outcome.verification.verified
    assert outcome.verification_tier == outcome.verification.tier
    assert outcome.confidence is not None and 0 <= outcome.confidence <= 1
    assert outcome.trajectory is not None
    assert outcome.trajectory.verification == outcome.verification
    assert HuntOutcome.model_validate_json(outcome.model_dump_json()) == outcome


def test_interprogram_d3_has_typed_loci_and_line_ownership(tools):
    outcome = _run(tools, "D3_contradictory", "d3")
    finding = outcome.finding
    assert finding.code_locus.is_interprocedural
    assert {locus.program for locus in finding.code_locus.loci} == {
        "CLOSPEN1",
        "CLOSPEN3",
    }
    assert {ref.program for ref in finding.labels.line_level} == {
        "CLOSPEN1",
        "CLOSPEN3",
    }

    dumped = finding.model_dump(mode="json")
    dumped["code_locus"] = {
        "programs": ["CLOSPEN1", "CLOSPEN3"],
        "paragraphs": ["2000-COMPUTE-PENALTY", "2000-PEN"],
        "line_span": [21, 34],
        "slice_vars": [],
        "is_interprocedural": True,
    }
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(dumped)


def test_insufficient_evidence_is_guarded_before_loop_emission(tools):
    outcome = _run(tools, "D1_stale_threshold", "insufficient_d1")
    assert outcome.abstained
    assert outcome.finding is None
    assert outcome.trajectory.finding is None
    assert "required tool evidence missing" in outcome.abstention_reason


def test_d2_requires_all_negative_scope_evidence_and_insertion_point(tools):
    outcome = _run(tools, "D2_missing_rule", "d2")
    assert outcome.verification_tier == VerificationTier.ENTAILMENT
    assert [step.tool for step in outcome.trajectory.steps] == [
        "grep",
        "find_callers",
        "find_callees",
        "slice_on",
    ]
    assert outcome.finding.labels.line_level[0].line == 20


def test_d6_delegates_to_existing_reachability_verifier(monkeypatch, tools):
    called = 0
    original = verify_module._tier2_reachability

    def recording_delegate(program, dead_para, tool_layer):
        nonlocal called
        called += 1
        return original(program, dead_para, tool_layer)

    monkeypatch.setattr(
        verify_module, "_tier2_reachability", recording_delegate
    )
    outcome = _run(tools, "D6_dead_code", "d6")
    assert called == 1
    assert outcome.verification_tier == VerificationTier.STATIC
    assert "forest_roots + reachable_from" in outcome.verification.evidence

    from cobol_archaeologist.agent.hunts import d6

    source = inspect.getsource(d6)
    assert "find_callers" not in source
    assert "entry_points" not in source
    assert "_tier2_reachability" not in source


def test_d6_caller_absence_does_not_make_fallthrough_live_code_dead(tools):
    assert tools.find_callers("FALLTHRU", "NEXT-PARA") == []
    outcome = _run(tools, "D6_dead_code", "d6_fallthrough")
    assert outcome.abstained and outcome.finding is None
    assert outcome.trajectory.finding is None
    assert "delegated reachability" in outcome.abstention_reason
    static_attempt = next(
        attempt
        for attempt in outcome.trajectory.verification.tier_attempts
        if attempt.tier == VerificationTier.STATIC
    )
    assert static_attempt.outcome == "refuted"
    assert "reachable" in static_attempt.detail.lower()


def test_d7_empty_scope_abstains_instead_of_defaulting_conformant(tools):
    clause = RegulationClause.model_validate(
        json.loads((CORPUS / "clauses.jsonl").read_text(encoding="utf-8").splitlines()[4])
    )
    outcome = get_hunt("D7_conformant").run(
        clause=clause,
        tools=tools,
        model=CachedDecisionModel(CACHE, cache_key="d7_empty"),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )
    assert outcome.abstained
    assert outcome.finding is None
    assert "positive" in outcome.abstention_reason


def test_mo0_d7_uses_semantics_not_edit_artifacts(tools):
    notice = (CORPUS / "NOTICE1.cbl").read_text(encoding="utf-8")
    assert "MO-0 COMMENT/STYLE EDIT" in notice and "DISPLAY 'OK= '" in notice
    outcome = _run(tools, "D7_conformant", "d7")
    assert not outcome.abstained
    assert outcome.finding.drift_type == "D7_conformant"

    from cobol_archaeologist.agent import policy

    assert "git history" in policy.__doc__.lower()
    assert "file mtimes" in policy.__doc__.lower()
    tree = ast.parse(inspect.getsource(policy))
    banned_imports = {"git", "gitpython", "subprocess"}
    assert not {
        node.names[0].name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    } & banned_imports
    assert not {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } & banned_imports
    assert not {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    } & {"stat", "st_mtime", "getmtime"}


@pytest.mark.parametrize(
    ("drift_type", "case"),
    [("D1_stale_threshold", "d1"), ("D5_boundary_error", "d5")],
)
def test_composite_d1_d5_target_path_resolves_to_leaf(tools, drift_type, case):
    finding = _run(tools, drift_type, case).finding
    assert finding.target_path
    leaf = resolve_path(
        finding.regulation_clause.current_value,
        finding.target_path,
    )
    assert leaf.kind != "composite"


def test_copybook_locus_and_temporal_pair_are_preserved(tools):
    new = _run(tools, "D1_stale_threshold", "d1")
    old = _run(tools, "D7_conformant", "temporal_old")
    assert any(locus.file == "WSDAYBAS.cpy" for locus in new.finding.code_locus.loci)
    assert new.finding.code_locus == old.finding.code_locus
    assert new.finding.labels.program_level == "drift"
    assert old.finding.labels.program_level == "conformant"
    assert new.finding.regulation_clause.version != old.finding.regulation_clause.version


def test_cached_hunts_are_offline_deterministic(tools):
    first = _run(tools, "D1_stale_threshold", "d1")
    second = _run(tools, "D1_stale_threshold", "d1")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
