"""T3.5 gates for the bounded, replayable, verify-before-emit agent loop."""

import inspect
from pathlib import Path

from cobol_archaeologist.agent.loop import InvestigationLoop
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
from cobol_archaeologist.model.prompt import (
    SYSTEM_PROMPT,
    AgentResponse,
    CachedDecisionModel,
)
from cobol_archaeologist.model.provider import _agent_response
from cobol_archaeologist.model.verify import LexicalEntailer, VerificationTier
from cobol_archaeologist.tools import RealToolLayer

FIX = Path(__file__).resolve().parent / "fixtures" / "agent"


def cached(name: str = "cached_responses.json") -> CachedDecisionModel:
    return CachedDecisionModel(FIX / name)


def run_golden(**kwargs) -> Trajectory:
    return InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=cached(),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
        **kwargs,
    ).run("Does the late-fee assessment comply with the current RBI rule?")


def test_late_fee_golden_is_verified_and_deterministic():
    trajectory = run_golden()
    assert not trajectory.abstained
    assert trajectory.finding is not None
    assert trajectory.finding.drift_type == "D3_contradictory"
    assert trajectory.verification is not None
    assert trajectory.verification.verified
    assert trajectory.verification.tier == VerificationTier.STATIC
    assert [attempt.outcome for attempt in trajectory.verification.tier_attempts] == [
        "unavailable",
        "verified",
    ]
    assert trajectory.model_id == cached().model_id
    assert trajectory.seed == cached().seed
    assert trajectory.final_answer

    golden = Trajectory.model_validate_json(
        (FIX / "golden_late_fee_trajectory.json").read_text(encoding="utf-8")
    )
    assert trajectory.model_dump(mode="json") == golden.model_dump(mode="json")


def test_trajectory_round_trips_and_contains_replay_inputs():
    trajectory = run_golden()
    replay = Trajectory.model_validate_json(trajectory.model_dump_json())
    assert replay == trajectory
    assert [step.tool for step in replay.steps] == [
        "grep",
        "read_paragraph",
        "search_regulations",
    ]
    assert all(step.arguments and step.observation_summary for step in replay.steps)
    assert len(replay.model_responses) == 4
    assert replay.finding.regulation_clause.clause_id == "23(5)"
    assert replay.verification.tier_attempts
    assert replay.final_answer == trajectory.final_answer


def test_tool_call_budget_is_enforced_before_call():
    trajectory = run_golden(
        budget=BudgetSpec(
            max_steps=8,
            max_tool_calls=0,
            max_tokens=500,
            wall_clock_timeout_s=30,
        )
    )
    assert trajectory.abstained and trajectory.budget_exhausted
    assert trajectory.finding is None
    assert trajectory.steps == []


def test_step_budget_is_enforced():
    trajectory = run_golden(
        budget=BudgetSpec(
            max_steps=1,
            max_tool_calls=8,
            max_tokens=500,
            wall_clock_timeout_s=30,
        )
    )
    assert trajectory.abstained and trajectory.budget_exhausted
    assert trajectory.finding is None
    assert len(trajectory.model_responses) == 1
    assert len(trajectory.steps) == 1


def test_token_budget_is_enforced_before_requested_tool_runs():
    trajectory = run_golden(
        budget=BudgetSpec(
            max_steps=8,
            max_tool_calls=8,
            max_tokens=1,
            wall_clock_timeout_s=30,
        )
    )
    assert trajectory.abstained and trajectory.budget_exhausted
    assert trajectory.finding is None
    assert trajectory.tokens_used == 24
    assert trajectory.steps == []


def test_wall_clock_budget_is_enforced():
    ticks = iter([0.0, 1.0, 2.0])
    trajectory = InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=cached(),
        entailer=LexicalEntailer(),
        clock=lambda: next(ticks),
        budget=BudgetSpec(
            max_steps=8,
            max_tool_calls=8,
            max_tokens=500,
            wall_clock_timeout_s=0.5,
        ),
    ).run("Does the late-fee assessment comply?")
    assert trajectory.abstained and trajectory.budget_exhausted
    assert trajectory.finding is None
    assert "wall" in trajectory.abstention_reason.lower()


def test_no_unverified_finding_is_ever_emitted():
    trajectory = InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=cached("unverified_responses.json"),
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    ).run("Return the deliberately unsupported finding.")
    assert trajectory.abstained
    assert trajectory.finding is None
    assert trajectory.verification is not None
    assert trajectory.verification.verified is False
    assert [attempt.outcome for attempt in trajectory.verification.tier_attempts] == [
        "unavailable",
        "refuted",
        "refuted",
    ]
    assert "must never be emitted" not in trajectory.final_answer


def test_real_stub_seam_is_constructor_only_and_loop_never_imports_tools():
    from cobol_archaeologist.agent import loop as loop_module

    source = inspect.getsource(loop_module)
    assert "cobol_archaeologist.tools" not in source
    stub = StubToolLayer(FIX / "corpus")
    real = RealToolLayer(corpus_root=FIX / "corpus", copybook_paths=[FIX / "corpus"])
    assert InvestigationLoop(stub, model=cached()).tools is stub
    assert InvestigationLoop(real, model=cached()).tools is real


def test_live_prompt_has_exact_tool_signatures_and_one_object_rule():
    prompt = " ".join(SYSTEM_PROMPT.split())
    assert "read_paragraph(program, name)" in prompt
    assert "find_callers(program, para)" in prompt
    assert "Return exactly one JSON object and stop" in prompt
    assert "never append an abstention" in prompt


class QueueModel:
    model_id = "offline-queue"
    temperature = 0.0
    seed = 0

    def __init__(self, responses):
        self.responses = list(responses)

    def respond(self, **_kwargs):
        return self.responses.pop(0)


def abstain(reason: str, tokens: int = 1) -> AgentResponse:
    return AgentResponse(
        kind="abstain",
        thought="Evidence is not yet sufficient.",
        abstention_reason=reason,
        final_answer=f"Abstained: {reason}",
        token_count=tokens,
    )


def tool(arguments: dict, tokens: int = 1) -> AgentResponse:
    return AgentResponse(
        kind="tool",
        thought="Acquire a bounded program observation.",
        tool="grep",
        arguments=arguments,
        token_count=tokens,
    )


def test_contract_rejection_repairs_once_and_persists_both_attempts():
    model = QueueModel(
        [
            _agent_response("not JSON", 3),
            tool({"pattern": "LATE-FEE-RATE"}, 5),
            abstain("search found no support", 7),
        ]
    )
    trajectory = InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=model,
        clock=lambda: 100.0,
        budget=BudgetSpec(max_steps=2, max_tokens=100),
    ).run("Check the scoped program.")

    assert trajectory.abstained and not trajectory.budget_exhausted
    assert trajectory.contract_repairs == 1
    assert len(trajectory.model_responses) == 3
    assert trajectory.model_responses[0].contract_error
    assert trajectory.model_responses[0].raw_provider_text == "not JSON"
    assert trajectory.model_responses[1].contract_error is None
    assert trajectory.tokens_used == 15
    assert len(trajectory.steps) == 1 and trajectory.steps[0].error is None


def test_second_contract_rejection_abstains_without_an_emission_path():
    trajectory = InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=QueueModel(
            [
                _agent_response("first invalid", 3),
                _agent_response("second invalid", 4),
            ]
        ),
        clock=lambda: 100.0,
    ).run("Check the scoped program.")

    assert trajectory.abstained and trajectory.finding is None
    assert trajectory.contract_repairs == 1
    assert trajectory.tokens_used == 7
    assert [bool(row.contract_error) for row in trajectory.model_responses] == [
        True,
        True,
    ]


def test_contract_repair_cannot_bypass_token_budget():
    model = QueueModel(
        [
            _agent_response("over budget", 3),
            tool({"pattern": "LATE-FEE-RATE"}, 1),
        ]
    )
    trajectory = InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=model,
        clock=lambda: 100.0,
        budget=BudgetSpec(max_steps=2, max_tokens=2),
    ).run("Check the scoped program.")

    assert trajectory.abstained and trajectory.budget_exhausted
    assert trajectory.contract_repairs == 0
    assert len(trajectory.model_responses) == 1
    assert len(model.responses) == 1


def test_pre_evidence_abstention_and_errored_tool_do_not_unlock_exit():
    model = QueueModel(
        [
            abstain("too early"),
            tool({}),  # missing grep pattern -> typed errored observation
            abstain("still too early"),
            tool({"pattern": "LATE-FEE-RATE"}),
            abstain("searched and found no supported finding"),
        ]
    )
    trajectory = InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=model,
        clock=lambda: 100.0,
        budget=BudgetSpec(max_steps=5, max_tokens=100),
    ).run("Check only LATEFEE1.")

    assert trajectory.abstained and not trajectory.budget_exhausted
    assert len(trajectory.model_responses) == 5
    assert trajectory.steps[0].error is not None
    assert trajectory.steps[1].error is None
    assert trajectory.abstention_reason == "searched and found no supported finding"


def test_repeated_pre_evidence_abstention_uses_normal_step_budget():
    trajectory = InvestigationLoop(
        StubToolLayer(FIX / "corpus"),
        model=QueueModel([abstain("one"), abstain("two")]),
        clock=lambda: 100.0,
        budget=BudgetSpec(max_steps=2, max_tokens=100),
    ).run("Check only LATEFEE1.")

    assert trajectory.abstained and trajectory.budget_exhausted
    assert trajectory.abstention_reason == "step budget exhausted"
    assert len(trajectory.model_responses) == 2
