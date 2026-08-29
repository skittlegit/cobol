"""T8.2 gates for the single-case adaptive D1-D7 agent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cobol_archaeologist.agent.adaptive import (
    ADAPTIVE_SYSTEM_PROMPT,
    CONFIG3_AGENT_BUDGET,
    AdaptiveAgent,
    AdaptiveOutcome,
    build_adaptive_prompt,
)
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.model.prompt import (
    AgentResponse,
    EvidenceLedgerNote,
)
from cobol_archaeologist.model.verify import LexicalEntailer
from cobol_archaeologist.schemas import RegulationClause

FIX = Path(__file__).resolve().parent / "fixtures" / "hunts"
CACHE = FIX / "cached_decisions.json"
CORPUS = FIX / "corpus"
VERIFIED_CASES = {
    "D1_stale_threshold": "d1",
    "D3_contradictory": "d3",
    "D5_boundary_error": "d5",
    "D6_dead_code": "d6",
    "D7_conformant": "d7",
}


def _rows(case: str) -> list[dict]:
    return json.loads(CACHE.read_text(encoding="utf-8"))[case]


def _clause(case: str) -> RegulationClause:
    final = next(row for row in reversed(_rows(case)) if row["kind"] == "finding")
    return RegulationClause.model_validate(final["prediction"]["regulation_clause"])


class _SequenceModel:
    model_id = "adaptive-offline-gate"
    temperature = 0.0
    seed = 0

    def __init__(self, responses: list[AgentResponse], hypothesis: str) -> None:
        self.responses = list(responses)
        self.hypothesis = hypothesis
        self.ledger: list[EvidenceLedgerNote] = []
        self.questions: list[str] = []

    def respond(self, **kwargs) -> AgentResponse:
        if not self.responses:
            raise RuntimeError("adaptive test response sequence exhausted")
        self.questions.append(kwargs["question"])
        response = self.responses.pop(0).model_copy(deep=True)
        prediction = response.prediction
        active = prediction.drift_type if prediction is not None else self.hypothesis
        known = {
            (
                note.observation_step,
                note.observation_sha256,
                note.hypothesis,
                note.bearing,
                note.rationale,
            )
            for note in self.ledger
        }
        for step in kwargs["transcript"]:
            if step.get("error") or not step.get("observation_summary"):
                continue
            summary = step["observation_summary"]
            note = EvidenceLedgerNote(
                observation_step=step["step"],
                observation_sha256=hashlib.sha256(summary.encode("utf-8")).hexdigest(),
                hypothesis=active,
                bearing="supports",
                rationale=f"Test model assessed this observation for {active}.",
            )
            key = (
                note.observation_step,
                note.observation_sha256,
                note.hypothesis,
                note.bearing,
                note.rationale,
            )
            if key not in known:
                self.ledger.append(note)
                known.add(key)
        return response.model_copy(
            update={"evidence_ledger": list(self.ledger)},
            deep=True,
        )


def _cached_model(case: str, hypothesis: str) -> _SequenceModel:
    return _SequenceModel(
        [AgentResponse.model_validate(row) for row in _rows(case)],
        hypothesis,
    )


def _run(case: str) -> AdaptiveOutcome:
    hypothesis = next(
        row["prediction"]["drift_type"]
        for row in reversed(_rows(case))
        if row["kind"] == "finding"
    )
    return AdaptiveAgent().run(
        clause=_clause(case),
        program_scope="offline fixture corpus",
        tools=StubToolLayer(CORPUS),
        model=_cached_model(case, hypothesis),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )


def test_adaptive_prompt_exposes_every_hypothesis_but_no_benchmark_answer():
    clause = _clause("d1")
    prompt = build_adaptive_prompt(clause, "CLOSPEN2")

    for drift_type in (
        "D1_stale_threshold",
        "D2_missing_rule",
        "D3_contradictory",
        "D4_stale_reference_data",
        "D5_boundary_error",
        "D6_dead_code",
        "D7_conformant",
    ):
        assert drift_type in ADAPTIVE_SYSTEM_PROMPT
    assert clause.clause_id in prompt
    assert clause.text in prompt
    assert "CLOSPEN2" in prompt
    assert "drift_910001" not in prompt
    assert "gold_rationale" not in prompt
    assert "provenance" not in prompt


def test_successor_prompt_encodes_observed_smoke_recovery_contracts():
    assert "Never put a COBOL program" in ADAPTIVE_SYSTEM_PROMPT
    assert "choose D3 rather than" in ADAPTIVE_SYSTEM_PROMPT
    assert "Choose D2 only when the regulated check itself is absent" in (
        ADAPTIVE_SYSTEM_PROMPT
    )
    assert "consider D7" in ADAPTIVE_SYSTEM_PROMPT
    assert "complete canonical missing or extra enum member verbatim" in (
        ADAPTIVE_SYSTEM_PROMPT
    )
    assert "Any positive observation from one of those four required tools" in (
        ADAPTIVE_SYSTEM_PROMPT
    )
    assert "If the bounded command returns `infrastructure_error`" in (
        ADAPTIVE_SYSTEM_PROMPT
    )
    assert "Copy every ledger step and observation SHA-256 exactly" in (
        ADAPTIVE_SYSTEM_PROMPT
    )


def test_clause_grounded_claim_passes_where_code_claim_does_not():
    premise = (
        "Past-due reporting or penal charges may be imposed only after an "
        "account remains past due for more than three days."
    )
    entailer = LexicalEntailer()

    code_claim = entailer.entail(
        premise,
        "LATEFEE2 paragraph 2000-FEE uses WS-DAYS-PAST-DUE >= 3 at line 21.",
    )
    clause_claim = entailer.entail(
        premise,
        "Penal charges may be imposed only after an account is past due for "
        "more than three days.",
    )

    assert not code_claim.entailment
    assert clause_claim.entailment


def test_config3_budget_is_the_frozen_work_order_budget():
    assert CONFIG3_AGENT_BUDGET.max_steps == 16
    assert CONFIG3_AGENT_BUDGET.max_tool_calls == 16
    assert CONFIG3_AGENT_BUDGET.max_tokens == 98_304
    assert CONFIG3_AGENT_BUDGET.wall_clock_timeout_s == 1_200


@pytest.mark.parametrize(("drift_type", "case"), VERIFIED_CASES.items())
def test_cached_single_case_investigations_emit_verified_ledgered_findings(
    drift_type, case
):
    outcome = _run(case)

    assert not outcome.abstained
    assert outcome.finding is not None
    assert outcome.finding.drift_type == drift_type
    assert outcome.verification is not None and outcome.verification.verified
    assert outcome.verification_tier == outcome.verification.tier
    assert outcome.confidence is not None
    assert outcome.evidence_ledger
    assert all(entry.hypothesis == drift_type for entry in outcome.evidence_ledger)
    assert all(entry.observation_step >= 1 for entry in outcome.evidence_ledger)
    assert all(entry.observation_sha256 for entry in outcome.evidence_ledger)
    assert AdaptiveOutcome.model_validate_json(outcome.model_dump_json()) == outcome


def test_under_evidenced_hypothesis_is_rejected_back_into_investigation():
    rows = [AgentResponse.model_validate(row) for row in _rows("d2")]
    responses = [rows[0], rows[-1], *rows[1:]]

    outcome = AdaptiveAgent().run(
        clause=_clause("d2"),
        program_scope="offline fixture corpus",
        tools=StubToolLayer(CORPUS),
        model=_SequenceModel(responses, "D2_missing_rule"),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )

    assert outcome.abstained
    assert [step.tool for step in outcome.trajectory.steps] == [
        "grep",
        "find_callers",
        "find_callees",
        "slice_on",
    ]
    assert len(outcome.trajectory.model_responses) == 6
    assert "Tier-3-only" in outcome.abstention_reason


def test_agent_has_no_cross_case_evidence_state():
    agent = AdaptiveAgent()
    first = agent.run(
        clause=_clause("d1"),
        program_scope="CLOSPEN2",
        tools=StubToolLayer(CORPUS),
        model=_cached_model("d1", "D1_stale_threshold"),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )
    second = agent.run(
        clause=_clause("d5"),
        program_scope="LIMIT1",
        tools=StubToolLayer(CORPUS),
        model=_cached_model("d5", "D5_boundary_error"),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )

    assert {entry.hypothesis for entry in first.evidence_ledger} == {
        "D1_stale_threshold"
    }
    assert {entry.hypothesis for entry in second.evidence_ledger} == {
        "D5_boundary_error"
    }
    assert first.evidence_ledger is not second.evidence_ledger


def test_model_authored_ledger_is_replayed_and_hypothesis_can_switch():
    d5_rows = [AgentResponse.model_validate(row) for row in _rows("d5")]
    early_d1 = AgentResponse.model_validate(_rows("d1")[-1])
    model = _SequenceModel(
        [d5_rows[0], early_d1, d5_rows[-1]],
        "D5_boundary_error",
    )

    outcome = AdaptiveAgent().run(
        clause=_clause("d5"),
        program_scope="offline fixture corpus",
        tools=StubToolLayer(CORPUS),
        model=model,
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )

    assert not outcome.abstained
    assert outcome.hypothesis == "D5_boundary_error"
    assert {note.hypothesis for note in outcome.evidence_ledger} == {
        "D1_stale_threshold",
        "D5_boundary_error",
    }
    assert "prior case-local model-authored evidence ledger" in model.questions[-1]
