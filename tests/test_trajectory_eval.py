"""T4.3 replay, evidence path, budget, and shortcut gates."""

from __future__ import annotations

import json
from pathlib import Path

from cobol_archaeologist.agent.policy import get_hunt
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.eval.trajectory import assess_trajectory
from cobol_archaeologist.model.prompt import CachedDecisionModel
from cobol_archaeologist.model.verify import LexicalEntailer
from cobol_archaeologist.schemas import RegulationClause

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "hunts"


def _d3_record() -> EvaluationRecord:
    clauses = [
        json.loads(line)
        for line in (FIX / "corpus" / "clauses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    clause = RegulationClause.model_validate(
        next(row for row in clauses if row["clause_id"] == "19")
    )
    outcome = get_hunt("D3_contradictory").run(
        clause=clause,
        tools=StubToolLayer(FIX / "corpus"),
        model=CachedDecisionModel(
            FIX / "cached_decisions.json",
            cache_key="d3",
        ),
        program_scope="CLOSPEN2,CLOSPEN3",
        entailer=LexicalEntailer(),
        clock=lambda: 100.0,
    )
    return EvaluationRecord(
        instance_id=outcome.finding.instance_id,
        gold=outcome.finding,
        prediction=outcome.finding,
        confidence=outcome.confidence,
        verification=outcome.verification,
        trajectory=outcome.trajectory,
        abstained=False,
        system_id="fixture",
        source_sha256="0" * 64,
        run_key="fixture:d3",
    )


def test_good_hunt_trajectory_is_replayable_and_grounded():
    assessment = assess_trajectory(_d3_record())

    assert assessment.replayable
    assert assessment.evidence_path_ok
    assert assessment.code_fact_ok
    assert assessment.budget_ok
    assert assessment.shortcut_free
    assert assessment.reasons == []


def test_budget_mismatch_and_shortcut_are_detected():
    record = _d3_record()
    bad_step = record.trajectory.steps[0].model_copy(
        update={"arguments": {"path": ".git/logs/HEAD", "mtime": True}}
    )
    bad_trajectory = record.trajectory.model_copy(
        update={
            "steps": [bad_step, *record.trajectory.steps[1:]],
            "tokens_used": record.trajectory.tokens_used + 1,
        }
    )
    bad = record.model_copy(update={"trajectory": bad_trajectory})
    assessment = assess_trajectory(bad)

    assert not assessment.budget_ok
    assert not assessment.shortcut_free
