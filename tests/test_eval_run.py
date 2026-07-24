"""T4.1 materialization, gold hiding, provider, and three-track seam gates."""

from __future__ import annotations

import ast
import json
import random
from pathlib import Path

import pytest

from cobol_archaeologist.agent.loop import InvestigationLoop
from cobol_archaeologist.benchmark.mutate import (
    ProgramSource,
    load_clause_records,
    mutate,
)
from cobol_archaeologist.eval.materialize import (
    MaterializationError,
    materialize,
)
from cobol_archaeologist.eval.metrics import evaluate
from cobol_archaeologist.eval.run import (
    EvaluationRunner,
    RunManifest,
    build_system_context,
    infrastructure_failure,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.prompt import CachedDecisionModel
from cobol_archaeologist.model.provider import (
    AnthropicDecisionModel,
    ProviderUnavailable,
)
from cobol_archaeologist.schemas import DriftInstance
from cobol_archaeologist.tools import RealToolLayer

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "benchmark" / "v1-pre" / "test.jsonl"
PROGRAMS = ROOT / "data" / "benchmark" / "seed" / "programs"
CLAUSES = ROOT / "data" / "regulations" / "clauses.jsonl"


def _rows() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in SPLIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _by_operator(operator: str) -> DriftInstance:
    return next(
        row
        for row in _rows()
        if (row.provenance.mutation or "").startswith(f"{operator};")
    )


@pytest.mark.parametrize("operator", ["MO-1", "MO-1×", "MO-6×"])
def test_materializes_local_copybook_and_interprogram_edits(operator):
    row = _by_operator(operator)
    source = materialize(row)
    old_new = {}
    for segment in row.provenance.mutation.split(";")[1:]:
        key, separator, value = segment.strip().partition("=")
        if separator and key in {"old", "new"}:
            old_new[key] = ast.literal_eval(value)

    assert source.main_file == row.provenance.base_program
    assert len(source.source_sha256) == 64
    assert old_new["new"] in "\n".join(source.files.values())
    if operator == "MO-1×":
        assert any(name.lower().endswith(".cpy") for name in source.files)
    if operator == "MO-6×":
        assert len([name for name in source.files if name.lower().endswith(".cbl")]) >= 2


def test_materializer_blanks_deletion_without_changing_line_count(tmp_path):
    row = _by_operator("MO-2")
    mutation = row.provenance.mutation or ""
    old = ast.literal_eval(
        next(
            segment.strip().partition("=")[2]
            for segment in mutation.split(";")[1:]
            if segment.strip().startswith("old=")
        )
    )
    locus = row.code_locus.loci[0]
    line_count = max(31, locus.line_span[1])
    lines = ["       01 FILLER PIC X.\n"] * line_count
    lines[locus.line_span[0] - 1] = f"       {old}\n"
    (tmp_path / row.provenance.base_program).write_text(
        "".join(lines),
        encoding="utf-8",
    )

    source = materialize(row, programs_root=tmp_path)

    assert old not in source.files[row.provenance.base_program]
    assert len(source.files[row.provenance.base_program].splitlines()) == line_count


def test_materializer_rejects_source_drift_and_ambiguity(tmp_path):
    row = _by_operator("MO-1")
    (tmp_path / row.provenance.base_program).write_text(
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {Path(row.provenance.base_program).stem}.\n",
        encoding="utf-8",
    )
    with pytest.raises(MaterializationError, match="matched 0"):
        materialize(row, programs_root=tmp_path)


def test_system_context_contains_no_gold_or_mutation_fields():
    row = _by_operator("MO-1")
    serialized = build_system_context(row).model_dump_json().lower()
    for prohibited in (
        "instance_id",
        "drift_type",
        "gold_rationale",
        "mutation",
        "old=",
        "new=",
        "line_level",
    ):
        assert prohibited not in serialized


def test_provider_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailable, match="ANTHROPIC_API_KEY"):
        AnthropicDecisionModel()


def test_week7_mutation_real_tool_agent_eval_seam(tmp_path):
    record = next(
        item
        for item in load_clause_records(CLAUSES)
        if item.record_id == "KYC-ckycr-update"
    )
    base = ProgramSource.from_path(
        PROGRAMS / "KYCSYNC2.cbl",
        touched_variables=("WS-DAYS-SINCE-UPD", "WS-SLA-STATUS"),
    )
    emitted = mutate(base, record, "MO-1", random.Random(2404))
    (tmp_path / emitted.source.filename).write_text(
        emitted.source.text,
        encoding="utf-8",
    )
    for name, text in emitted.source.files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    responses = tmp_path / "responses.json"
    responses.write_text(
        json.dumps(
            [
                {
                    "kind": "tool",
                    "thought": "Find the mutated SLA literal through the real facade.",
                    "tool": "grep",
                    "arguments": {"pattern": "14"},
                    "token_count": 8,
                },
                {
                    "kind": "abstain",
                    "thought": "This seam checks transport, not model accuracy.",
                    "abstention_reason": "seam fixture stops after real evidence",
                    "final_answer": "Abstained after real-tool seam evidence.",
                    "token_count": 8,
                },
            ]
        ),
        encoding="utf-8",
    )
    tools = RealToolLayer(corpus_root=tmp_path, copybook_paths=[tmp_path])
    trajectory = InvestigationLoop(
        tools,
        model=CachedDecisionModel(responses),
        clock=lambda: 100.0,
    ).run("Check the CKYCR update deadline.")

    assert [step.tool for step in trajectory.steps] == ["grep"]
    assert trajectory.steps[0].error is None
    assert "14" in trajectory.steps[0].observation_summary

    evaluation = EvaluationRecord(
        instance_id=emitted.instance.instance_id,
        gold=emitted.instance,
        trajectory=trajectory,
        abstained=True,
        abstention_reason=trajectory.abstention_reason,
        system_id="week7-seam",
        source_sha256="0" * 64,
        run_key="week7-seam",
    )
    score = evaluate([evaluation])["overall"]["t1_detection"]
    assert score["fn"] == 1
    assert score["answer_rate"] == 0


def test_append_only_runner_resumes_without_duplicate_execution(tmp_path):
    rows = _rows()[:2]
    runner = EvaluationRunner(
        tmp_path / "records.jsonl",
        tmp_path / "manifest.json",
    )
    manifest = RunManifest(
        system_id="fixture",
        model_id="none",
        repository_commit="a" * 40,
        prompt_version="test",
        split_path="test.jsonl",
        total=2,
    )
    calls: list[str] = []

    def execute(gold, context, key):
        calls.append(gold.instance_id)
        assert "drift_type" not in context.model_dump_json()
        return infrastructure_failure(
            gold,
            system_id="fixture",
            source_sha256="0" * 64,
            key=key,
            reason="fixture has no provider",
        )

    key_factory = lambda gold: f"key:{gold.instance_id}"
    first = runner.run(
        rows,
        manifest=manifest,
        key_factory=key_factory,
        executor=execute,
    )
    second = runner.run(
        rows,
        manifest=manifest,
        key_factory=key_factory,
        executor=execute,
    )

    assert len(first) == len(second) == 2
    assert calls == [row.instance_id for row in rows]
    assert len((tmp_path / "records.jsonl").read_text().splitlines()) == 2
