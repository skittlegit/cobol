"""Offline gates for the resumable three-system M4 live runner."""

from pathlib import Path

import pytest

from cobol_archaeologist.eval import live as live_module
from cobol_archaeologist.eval.baselines import DenseRAGContext
from cobol_archaeologist.eval.live import (
    _assert_matching_smoke,
    baseline_question,
    bounded_code_context,
    run_live_system,
)
from cobol_archaeologist.eval.materialize import MaterializedSource
from cobol_archaeologist.eval.run import (
    CONFIG2_SMOKE_IDS,
    CONFIG2_SMOKE_SEED,
    RunManifest,
)
from cobol_archaeologist.eval.schemas import RunValidity
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "benchmark" / "v1-pre" / "test.jsonl"


def _row() -> DriftInstance:
    return DriftInstance.model_validate_json(
        next(line for line in SPLIT.read_text(encoding="utf-8").splitlines() if line)
    )


def test_dense_baseline_question_contains_no_hidden_gold_fields():
    gold = _row()
    visible = DenseRAGContext(
        clause_query=gold.regulation_clause.text,
        retrieved_clauses=[],
        program="0001: IDENTIFICATION DIVISION.",
    )

    rendered = baseline_question("dense_rag", visible)

    for hidden in (
        gold.instance_id,
        gold.drift_type,
        gold.gold_rationale,
        gold.provenance.mutation,
    ):
        if hidden:
            assert hidden not in rendered
    assert gold.regulation_clause.text in rendered


def test_bounded_code_context_is_query_driven_and_line_bounded():
    irrelevant = [f"       01 FILLER-{index:03d} PIC X." for index in range(80)]
    relevant = [
        "       IF CREDIT-LIMIT > 5000",
        "           MOVE 'REVIEW' TO ACCOUNT-STATUS",
        "       END-IF",
    ]
    lines = irrelevant[:40] + relevant + irrelevant[40:]
    materialized = MaterializedSource(
        main_file="ACCOUNT.cbl",
        files={"ACCOUNT.cbl": "\n".join(lines) + "\n"},
        source_sha256="0" * 64,
    )

    context = bounded_code_context(
        materialized,
        "credit limit must not exceed 5000",
        max_lines=40,
    )

    assert "CREDIT-LIMIT > 5000" in context
    numbered_code_lines = [
        line for line in context.splitlines() if line[:4].isdigit()
    ]
    assert len(numbered_code_lines) <= 40
    assert "mutation" not in context.lower()


def _manifest(
    *,
    run_mode="full",
    total=204,
    effort="low",
    smoke_seed=CONFIG2_SMOKE_SEED,
    smoke_instance_ids=None,
) -> RunManifest:
    if smoke_instance_ids is None:
        smoke_instance_ids = list(CONFIG2_SMOKE_IDS)
    return RunManifest(
        system_id="dense_rag",
        provider="openai",
        model_id="gpt-5.6-luna",
        decoding={
            "temperature": 0.0,
            "reasoning_effort": effort,
            "seed": None,
        },
        budgets={"max_steps": 1},
        repository_commit="a" * 40,
        input_revision="input-v1",
        tool_version="tools@abc",
        prompt_version="prompt-v3",
        split_path="data/test.jsonl",
        split_sha256="b" * 64,
        schema_version="3",
        run_mode=run_mode,
        smoke_rows=7 if run_mode == "smoke" else None,
        smoke_seed=smoke_seed,
        smoke_instance_ids=smoke_instance_ids,
        total=total,
    )


def test_full_run_refuses_before_materialization_without_matching_smoke(
    monkeypatch,
    tmp_path,
):
    touched = False

    def forbidden(_rows):
        nonlocal touched
        touched = True
        raise AssertionError("materialization must be downstream of smoke gate")

    monkeypatch.setattr(live_module, "_materialize_all", forbidden)
    monkeypatch.setattr(
        live_module,
        "OpenAIDecisionModel",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("offline gate must not construct a credential reader")
        ),
    )
    with pytest.raises(RuntimeError, match="requires a successful matching"):
        run_live_system(
            "dense_rag",
            rows=[_row()],
            model_id="gpt-5.6-luna",
            smoke_seed=CONFIG2_SMOKE_SEED,
            output_dir=tmp_path,
        )
    assert not touched


def test_matching_smoke_is_exact_and_must_be_valid(tmp_path):
    expected = _manifest()
    smoke = _manifest(run_mode="smoke", total=7)
    smoke.completed_run_keys = [f"key-{index}" for index in range(7)]
    smoke.validity = RunValidity(
        completed_rows=7,
        available_rows=7,
        infrastructure_failures=0,
        provider_turns=7,
        contract_rejections=0,
        contract_rejection_rate=0.0,
        non_null_predictions=1,
        non_null_prediction_rate=1 / 7,
        status="VALID",
    )
    path = tmp_path / "smoke" / "dense_rag.manifest.json"
    path.parent.mkdir()
    path.write_text(smoke.model_dump_json(), encoding="utf-8")

    _assert_matching_smoke(expected, output_dir=tmp_path)

    mismatched = _manifest(run_mode="smoke", total=7, effort="medium")
    mismatched.completed_run_keys = smoke.completed_run_keys
    mismatched.validity = smoke.validity
    path.write_text(mismatched.model_dump_json(), encoding="utf-8")
    with pytest.raises(RuntimeError, match="decoding"):
        _assert_matching_smoke(expected, output_dir=tmp_path)

    mismatched = _manifest(
        run_mode="smoke",
        total=7,
        smoke_instance_ids=list(reversed(smoke.smoke_instance_ids)),
    )
    mismatched.completed_run_keys = smoke.completed_run_keys
    mismatched.validity = smoke.validity
    path.write_text(mismatched.model_dump_json(), encoding="utf-8")
    with pytest.raises(RuntimeError, match="smoke_instance_ids"):
        _assert_matching_smoke(expected, output_dir=tmp_path)


def test_smoke_artifacts_never_use_headline_paths(monkeypatch, tmp_path):
    captured = {}

    def fake_run(self, rows, **_kwargs):
        captured["records"] = self.records_path
        captured["manifest"] = self.manifest_path
        captured["run_manifest"] = _kwargs["manifest"]
        return []

    monkeypatch.setattr(live_module.EvaluationRunner, "run", fake_run)
    monkeypatch.setattr(
        live_module,
        "_materialize_all",
        lambda rows: ({}, {row.instance_id: "fixture" for row in rows}),
    )
    rows = [
        DriftInstance.model_validate_json(line)
        for line in SPLIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_live_system(
        "agent",
        rows=rows,
        model_id="qwen3:4b",
        provider="ollama",
        output_dir=tmp_path,
        regulation_search=object(),
        entailer=object(),
        smoke=7,
        smoke_seed=CONFIG2_SMOKE_SEED,
    )

    assert captured["records"].parent == tmp_path / "smoke"
    assert captured["manifest"].parent == tmp_path / "smoke"
    assert not (tmp_path / "agent.jsonl").exists()
    assert captured["run_manifest"].provider == "ollama"
    assert captured["run_manifest"].model_id == "qwen3:4b"
    assert captured["run_manifest"].decoding["temperature"] == 0.0
    assert captured["run_manifest"].decoding["thinking"] is False
    assert captured["run_manifest"].decoding["seed"] == 2601
    assert captured["run_manifest"].decoding[
        "min_successful_observations_by_drift_type"
    ] == {
        "D1_stale_threshold": 1,
        "D2_missing_rule": 4,
        "D3_contradictory": 2,
        "D4_stale_reference_data": 1,
        "D5_boundary_error": 1,
        "D6_dead_code": 1,
        "D7_conformant": 1,
    }
