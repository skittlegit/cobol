"""D1-D7 evidence guards and verifier, replayed through the production detector."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.agent.hunts.d3 import D3Hunt
from cobol_archaeologist.agent.hunts.d4 import D4Hunt
from cobol_archaeologist.agent.policy import HUNT_REGISTRY, get_hunt
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.eval.detector import CaseOutcome
from cobol_archaeologist.model import verify as verify_module
from cobol_archaeologist.model.prompt import HUNT_PROMPTS, SYSTEM_PROMPT, AgentResponse
from cobol_archaeologist.model.verify import VerificationTier
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction, RegulationClause
from tests.replay import replay

FIX = Path(__file__).resolve().parent / "fixtures" / "hunts"
CACHE = FIX / "cached_decisions.json"
CORPUS = FIX / "corpus"
M4_REJECTED = FIX / "m4_rejected_rows.jsonl"
POSITIVE_CASES = {
    "D1_stale_threshold": "d1",
    "D2_missing_rule": "d2",
    "D3_contradictory": "d3",
    "D4_stale_reference_data": "d4",
    "D5_boundary_error": "d5",
    "D6_dead_code": "d6",
    "D7_conformant": "d7",
}
VERIFIED_CASES = {
    drift_type: case
    for drift_type, case in POSITIVE_CASES.items()
    if drift_type not in {"D2_missing_rule", "D4_stale_reference_data"}
}


@pytest.fixture()
def tools() -> StubToolLayer:
    return StubToolLayer(CORPUS)


def _rows(case: str) -> list[dict]:
    return json.loads(CACHE.read_text(encoding="utf-8"))[case]


def _corpus_clause(index: int) -> RegulationClause:
    lines = (CORPUS / "clauses.jsonl").read_text(encoding="utf-8").splitlines()
    return RegulationClause.model_validate(json.loads(lines[index]))


def _clause(case: str) -> RegulationClause:
    final = next(
        (row for row in reversed(_rows(case)) if row["kind"] == "finding"), None
    )
    if final is None:
        return _corpus_clause(0)
    return RegulationClause.model_validate(final["prediction"]["regulation_clause"])


def _run(tools: StubToolLayer, case: str, clause: RegulationClause | None = None):
    return replay(_rows(case), clause=clause or _clause(case), tools=tools)


def _null_value_rows(case: str) -> tuple[RegulationClause, list[dict]]:
    clause = _clause(case).model_copy(update={"current_value": None})
    rows = json.loads(json.dumps(_rows(case)))
    for row in rows:
        if row.get("prediction"):
            row["prediction"]["regulation_clause"] = clause.model_dump(mode="json")
            row["prediction"]["target_path"] = None
    return clause, rows


def _m4_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in M4_REJECTED.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_registry_has_exactly_one_hunt_per_drift_class():
    assert set(HUNT_REGISTRY) == set(POSITIVE_CASES)
    assert set(HUNT_PROMPTS) == set(POSITIVE_CASES)
    assert all(hunt.drift_type == key for key, hunt in HUNT_REGISTRY.items())


def test_only_verifier_constructs_verification_results_or_mutates_their_tier():
    source_root = Path(__file__).resolve().parents[1] / "src" / "cobol_archaeologist"
    verifier = source_root / "model" / "verify.py"
    for path in source_root.rglob("*.py"):
        if path == verifier:
            continue
        source = path.read_text(encoding="utf-8")
        assert "VerificationResult(" not in source, path
        assert 'model_copy(update={"tier"' not in source, path


@pytest.mark.parametrize(("drift_type", "case"), VERIFIED_CASES.items())
def test_each_class_emits_schema_valid_verified_finding(tools, drift_type, case):
    outcome = _run(tools, case)
    assert not outcome.abstained, outcome.abstention_reason
    assert isinstance(outcome.finding, DriftPrediction)
    assert outcome.finding.drift_type == drift_type
    assert outcome.verification is not None and outcome.verification.verified
    assert outcome.verification_tier == outcome.verification.tier
    assert outcome.confidence is not None and 0 <= outcome.confidence <= 1
    assert outcome.trajectory.verification == outcome.verification
    assert CaseOutcome.model_validate_json(outcome.model_dump_json()) == outcome


def test_interprogram_d3_has_typed_loci_and_line_ownership(tools):
    finding = _run(tools, "d3").finding
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


def test_d3_counts_unique_paragraph_reads_and_accepts_bypass_wording():
    payload = json.loads(json.dumps(_rows("d3")[-1]))
    first = payload["prediction"]["code_locus"]["loci"][0]
    payload["prediction"]["code_locus"]["loci"] = [
        first,
        {**first, "line_span": [first["line_span"][1], first["line_span"][1]]},
    ]
    payload["prediction"]["code_locus"]["is_interprocedural"] = False
    payload["prediction"]["labels"]["line_level"] = [
        {"program": first["program"], "line": first["line_span"][0], "file": first["file"]}
    ]
    payload["prediction"]["rationale"] = "The downstream action bypasses the invalid state."
    response = AgentResponse.model_validate(payload)
    errors = D3Hunt().validate_response(
        response,
        [
            {
                "step": 1,
                "tool": "read_paragraph",
                "arguments": {"program": first["program"], "name": first["paragraph"]},
                "observation_summary": "{}",
                "observation_truncated": False,
                "error": None,
            }
        ],
        response.prediction.regulation_clause,
    )
    assert not any("read_paragraph calls" in error for error in errors)
    assert not any("conflicting outcomes" in error for error in errors)


def test_finding_without_observations_abstains(tools):
    outcome = _run(tools, "insufficient_d1")
    assert outcome.abstained
    assert outcome.finding is None
    assert outcome.verification is None


@pytest.mark.parametrize("case", ["d2", "d4"])
def test_entailment_only_findings_abstain_despite_class_evidence(tools, case):
    outcome = _run(tools, case)
    assert outcome.abstained
    assert outcome.finding is None
    assert outcome.verification_tier == VerificationTier.ENTAILMENT
    assert "Tier-3-only" in outcome.abstention_reason
    if case == "d2":
        assert [step.tool for step in outcome.trajectory.steps] == [
            "grep",
            "find_callers",
            "find_callees",
            "slice_on",
        ]


def test_program_filename_is_normalized_using_real_rejected_row():
    row = next(row for row in _m4_rows() if row["instance_id"] == "drift_000008")
    raw = next(
        response
        for response in row["trajectory"]["model_responses"]
        if response["kind"] == "finding"
    )
    response = AgentResponse.model_validate(raw)
    get_hunt("D1_stale_threshold").validate_response(
        response, row["trajectory"]["steps"], response.prediction.regulation_clause
    )
    assert all(locus.file is None for locus in response.prediction.code_locus.loci)
    assert all(ref.file is None for ref in response.prediction.labels.line_level)
    assert "SourceLocus.file normalized" in response.thought
    assert '"file":"BOIDENT1.cbl"' in response.raw_provider_text


def test_copybook_guard_rows_split_47_program_files_and_two_copybooks():
    affected = normalized = 0
    still_guarded: set[str] = set()
    for row in _m4_rows():
        reason = row["trajectory"].get("abstention_reason") or ""
        if "required tool evidence missing: resolve_copybook" not in reason:
            continue
        affected += 1
        response = AgentResponse.model_validate(
            next(
                item
                for item in row["trajectory"]["model_responses"]
                if item["kind"] == "finding"
            )
        )
        errors = get_hunt(response.prediction.drift_type).validate_response(
            response, row["trajectory"]["steps"], response.prediction.regulation_clause
        )
        normalized += "SourceLocus.file normalized" in response.thought
        if any("resolve_copybook" in error for error in errors):
            still_guarded.add(row["instance_id"])
    assert affected == 49
    assert normalized == 47
    assert still_guarded == {"drift_323235", "drift_479980"}


def test_d4_without_copybook_locus_does_not_require_copybook_observation():
    payload = json.loads(json.dumps(_rows("d4")[-1]))
    for locus in payload["prediction"]["code_locus"]["loci"]:
        locus["file"] = None
    for ref in payload["prediction"]["labels"]["line_level"]:
        ref["file"] = None
    response = AgentResponse.model_validate(payload)
    errors = D4Hunt().validate_response(
        response, [], response.prediction.regulation_clause
    )
    assert not any("resolve_copybook" in error for error in errors)


def test_evidence_minimum_is_derived_from_drift_class_and_locus_count():
    from cobol_archaeologist.agent.policy import evidence_minimum_for

    assert evidence_minimum_for("D1_stale_threshold", locus_count=1) == 1
    assert evidence_minimum_for("D5_boundary_error", locus_count=1) == 1
    assert evidence_minimum_for("D2_missing_rule", locus_count=1) == 4
    assert evidence_minimum_for("D3_contradictory", locus_count=3) == 3


def test_system_prompt_disambiguates_source_file():
    assert '"file": null' in SYSTEM_PROMPT
    assert '"file": "WSDAYBAS.cpy"' in SYSTEM_PROMPT


def test_value_requirement_is_scoped_to_d1_d4_d5_prompts() -> None:
    for drift_type in ("D1_stale_threshold", "D4_stale_reference_data", "D5_boundary_error"):
        assert "resolved current_value is required" in HUNT_PROMPTS[drift_type]
    for drift_type in ("D2_missing_rule", "D6_dead_code", "D7_conformant"):
        assert "current_value may be null" in HUNT_PROMPTS[drift_type]


@pytest.mark.parametrize("case", ["d6", "d7"])
def test_d6_d7_null_current_value_can_validate_positive_evidence(tools, case):
    clause, rows = _null_value_rows(case)
    outcome = replay(rows, clause=clause, tools=tools)
    assert not outcome.abstained, outcome.abstention_reason
    assert outcome.finding is not None


def test_d2_null_current_value_has_no_value_leaf_guard(tools):
    clause, rows = _null_value_rows("d2")
    outcome = replay(rows, clause=clause, tools=tools)
    assert outcome.abstained
    assert "Tier-3-only" in outcome.abstention_reason
    assert "current value" not in outcome.abstention_reason.lower()


def test_d1_null_current_value_still_abstains_on_value_guard(tools):
    clause, rows = _null_value_rows("d1")
    outcome = replay(rows, clause=clause, tools=tools)
    assert outcome.abstained
    assert "D1 requires a current clause value" in outcome.abstention_reason


def test_d6_delegates_to_existing_reachability_verifier(monkeypatch, tools):
    called = 0
    original = verify_module._tier2_reachability

    def recording_delegate(program, dead_para, tool_layer):
        nonlocal called
        called += 1
        return original(program, dead_para, tool_layer)

    monkeypatch.setattr(verify_module, "_tier2_reachability", recording_delegate)
    outcome = _run(tools, "d6")
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
    outcome = _run(tools, "d6_fallthrough")
    assert outcome.abstained and outcome.finding is None
    static_attempt = next(
        attempt
        for attempt in outcome.verification.tier_attempts
        if attempt.tier == VerificationTier.STATIC
    )
    assert static_attempt.outcome == "refuted"
    assert "reachable" in static_attempt.detail.lower()


def test_d7_abstention_without_evidence_is_not_conformant(tools):
    outcome = replay(_rows("d7_empty"), clause=_corpus_clause(4), tools=tools)
    assert outcome.abstained
    assert outcome.finding is None


def test_mo0_d7_uses_semantics_not_edit_artifacts(tools):
    notice = (CORPUS / "NOTICE1.cbl").read_text(encoding="utf-8")
    assert "MO-0 COMMENT/STYLE EDIT" in notice and "DISPLAY 'OK= '" in notice
    outcome = _run(tools, "d7")
    assert not outcome.abstained
    assert outcome.finding.drift_type == "D7_conformant"

    from cobol_archaeologist.agent import policy

    assert "git history" in policy.__doc__.lower()
    assert "file mtimes" in policy.__doc__.lower()
    tree = ast.parse(inspect.getsource(policy))
    banned = {"git", "gitpython", "subprocess"}
    assert not {
        node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)
    } & banned
    assert not {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } & banned


def test_composite_d1_d5_target_path_resolves_to_leaf(tools):
    for case in ("d1", "d5"):
        finding = _run(tools, case).finding
        assert finding.target_path is not None
        assert finding.regulation_clause.current_value.kind == "composite"


def test_temporal_old_side_replays(tools):
    outcome = _run(tools, "temporal_old")
    assert outcome.trajectory.steps
