"""T3.5 gates for the bounded, replayable, verify-before-emit agent loop."""

import inspect
from pathlib import Path

from cobol_archaeologist.agent.loop import InvestigationLoop
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
from cobol_archaeologist.model.prompt import CachedDecisionModel
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
