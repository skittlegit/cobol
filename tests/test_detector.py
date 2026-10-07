"""Detector prompt, host-computed evidence ledger, and final-answer checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.eval import codex
from cobol_archaeologist.eval.detector import (
    DetectorEnvelope,
    SubmittedCase,
    build_prompt,
    host_ledger,
)
from cobol_archaeologist.schemas import RegulationClause
from tests.replay import ALIAS, replay, run_tools, submitted_case

FIX = Path(__file__).resolve().parent / "fixtures" / "hunts"
CORPUS = FIX / "corpus"
DRIFT_TYPES = (
    "D1_stale_threshold",
    "D2_missing_rule",
    "D3_contradictory",
    "D4_stale_reference_data",
    "D5_boundary_error",
    "D6_dead_code",
    "D7_conformant",
)


def _rows(case: str) -> list[dict]:
    return json.loads((FIX / "cached_decisions.json").read_text(encoding="utf-8"))[case]


def _clause(case: str) -> RegulationClause:
    final = next(row for row in reversed(_rows(case)) if row["kind"] == "finding")
    return RegulationClause.model_validate(final["prediction"]["regulation_clause"])


def test_prompt_lists_every_class_and_the_clause_but_no_answer():
    clause = _clause("d1")
    prompt = build_prompt(
        alias=ALIAS, clause=clause, program_scope="CLOSPEN2", tool_command="BRIDGE"
    )
    for drift_type in DRIFT_TYPES:
        assert drift_type in prompt
    assert clause.text in prompt
    assert f"BRIDGE {ALIAS} TOOL" in prompt
    assert f"BRIDGE {ALIAS} check_finding" in prompt
    visible = prompt.split("Detector-visible case:", 1)[1]
    for forbidden in ("gold_rationale", "mutation", "provenance", "drift_type", "labels"):
        assert forbidden not in visible


def test_prompt_never_asks_the_model_to_copy_hashes():
    prompt = build_prompt(
        alias=ALIAS, clause=_clause("d1"), program_scope="X", tool_command="BRIDGE"
    )
    assert "SHA-256" not in prompt
    assert "do not write hashes" in prompt


def test_answer_schema_has_no_hash_or_identity_fields():
    schema = json.dumps(codex.strict_schema(DetectorEnvelope))
    assert "observation_sha256" not in schema
    assert "instance_id" not in schema
    assert "regulation_clause" not in schema


def test_host_ledger_computes_hashes_from_trusted_observations():
    tools = StubToolLayer(CORPUS)
    logs = run_tools(_rows("d1"), tools)
    case = submitted_case(_rows("d1")[-1], logs)
    from cobol_archaeologist.eval.detector import _steps

    ledger, errors = host_ledger(case.evidence_ledger, _steps(logs, ALIAS))
    assert not errors
    for note, log in zip(ledger, logs, strict=True):
        assert (
            note.observation_sha256
            == hashlib.sha256(log.observation_summary.encode()).hexdigest()
        )


def test_citing_a_missing_observation_is_rejected():
    tools = StubToolLayer(CORPUS)
    rows = _rows("d1")
    logs = run_tools(rows, tools)
    case = submitted_case(rows[-1], logs)
    payload = case.model_dump()
    payload["evidence_ledger"][0]["observation_step"] = 99
    from cobol_archaeologist.eval.detector import finalize_case
    from cobol_archaeologist.model.verify import LexicalEntailer

    outcome = finalize_case(
        SubmittedCase.model_validate(payload),
        clause=_clause("d1"),
        program_scope="CLOSPEN2",
        instance_id="drift_910001",
        logs=logs,
        tools=tools,
        entailer=LexicalEntailer(),
        token_count=0,
        token_count_recorded=False,
    )
    assert outcome.abstained
    assert "ledger step 99 is not a successful observation" in outcome.abstention_reason


def test_verified_finding_carries_host_ledger_and_confidence():
    outcome = replay(_rows("d1"), clause=_clause("d1"), tools=StubToolLayer(CORPUS))
    assert not outcome.abstained, outcome.abstention_reason
    assert outcome.finding.instance_id == "drift_910001"
    assert outcome.finding.regulation_clause == _clause("d1")
    assert outcome.evidence_ledger
    assert outcome.confidence is not None


def test_model_cannot_choose_the_clause_or_identity():
    rows = json.loads(json.dumps(_rows("d1")))
    rows[-1]["prediction"]["instance_id"] = "drift_123456"
    outcome = replay(rows, clause=_clause("d1"), tools=StubToolLayer(CORPUS))
    assert outcome.finding.instance_id == "drift_910001"
