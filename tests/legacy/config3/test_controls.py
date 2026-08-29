"""Offline gates for the configuration-3 Luna/max control runner."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from cobol_archaeologist.eval.codex_batch import (
    CodexBaselineEnvelope,
    ParsedCodexEvents,
    SubmittedBaselineCase,
    SubmittedResponse,
)
from cobol_archaeologist.eval.codex_live import CodexTaskExecution, batch_size_for
from cobol_archaeologist.eval.config3_controls import (
    CONTROL_SYSTEMS,
    MODEL_ID,
    REASONING_EFFORT,
    build_control_contexts,
    build_control_seal,
    control_batch_key,
    ensure_control_seal,
    run_config3_control,
)
from cobol_archaeologist.eval.config3_live import (
    CONFIG3_SYSTEMS,
    PHASE5_AGGREGATE_PATHS,
    PHASE5_BASELINE_PATHS,
    Config3RunFreeze,
    canonical_sha256,
    expected_codex_request_sha256,
    runtime_source_sha256,
    seeded_dev_smoke,
)
from cobol_archaeologist.eval.live import AGENT_BUDGET, BASELINE_BUDGET
from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.model.verify import LexicalEntailer
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[3]


def _smoke_rows() -> list[DriftInstance]:
    def load(name: str) -> list[DriftInstance]:
        path = ROOT / "data" / "benchmark" / "v1" / f"{name}.jsonl"
        return [
            DriftInstance.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    return seeded_dev_smoke(load("dev"), fallback_rows=load("train"))


def _freeze(rows: list[DriftInstance]) -> Config3RunFreeze:
    source_hashes = {row.instance_id: materialize(row).source_sha256 for row in rows}
    return Config3RunFreeze(
        provider="chatgpt-codex",
        authentication="ChatGPT",
        prompt_version="m4-config3-adaptive-v1",
        repository_commit="a" * 40,
        runtime_source_sha256=runtime_source_sha256(ROOT),
        codex_cli_version="codex 1.2.3",
        wsl_distribution="Ubuntu",
        transport="wsl",
        codex_binary="/home/deepa/.local/bin/codex-x86_64-unknown-linux-musl",
        max_workers=3,
        systems=CONFIG3_SYSTEMS,
        budgets={
            "agent": AGENT_BUDGET.model_dump(mode="json"),
            "adaptive_agent": {},
            **{
                system: BASELINE_BUDGET.model_dump(mode="json")
                for system in CONTROL_SYSTEMS
                if system != "agent"
            },
        },
        batch_sizes={system: batch_size_for(system) for system in CONTROL_SYSTEMS}
        | {"adaptive_agent": 1},
        identity_hashes={"prompt": "b" * 64},
        phase5_baseline_sha256={
            path.as_posix(): hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in PHASE5_BASELINE_PATHS
        },
        phase5_aggregate_sha256={
            path.as_posix(): hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in PHASE5_AGGREGATE_PATHS
        },
        chatgpt_account_sha256="9" * 64,
        dev_split_path="data/benchmark/v1/dev.jsonl",
        dev_split_sha256="c" * 64,
        train_split_path="data/benchmark/v1/train.jsonl",
        train_split_sha256="1" * 64,
        test_split_path="data/benchmark/v1/test.jsonl",
        test_split_sha256="d" * 64,
        t6_v2_path="data/benchmark/t6-v2/manifest.json",
        t6_v2_sha256="e" * 64,
        smoke_seed=20_260_824,
        smoke_instance_ids=tuple(row.instance_id for row in rows),
        dev_order=tuple(row.instance_id for row in rows),
        test_order=("test-1",),
        t6_order=("t6-1",),
        t6_source_inputs={},
        source_sha256=source_hashes,
    )


def _patch_environment(monkeypatch) -> None:
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_controls.repository_commit",
        lambda _root: "a" * 40,
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_controls._check_chatgpt_login",
        lambda **_kwargs: "Logged in using ChatGPT",
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_controls._wsl",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=b"codex 1.2.3\n",
            stderr=b"",
        ),
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_controls._wsl_chatgpt_account_sha256",
        lambda **_kwargs: "9" * 64,
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_controls.prepare_support_runtime",
        lambda **_kwargs: "/support",
    )


def _abstained_execution(prompt: str) -> CodexTaskExecution:
    aliases = sorted(set(re.findall(r'"alias":"(drift_9\d{5})"', prompt)))
    response = SubmittedResponse(
        kind="abstain",
        thought="The bounded context does not support a finding.",
        prediction=None,
        claim=None,
        exec_probe=None,
        static_claim=None,
        abstention_reason="insufficient evidence",
        final_answer="Abstained: insufficient evidence",
    )
    message = CodexBaselineEnvelope(
        results=[
            SubmittedBaselineCase(alias=alias, clause_index=None, response=response)
            for alias in aliases
        ]
    ).model_dump_json(by_alias=True)
    events = [{"type": "turn.completed"}]
    return CodexTaskExecution(
        task_root="/task/control",
        parsed=ParsedCodexEvents(
            final_message=message,
            usage={"input_tokens": 100, "output_tokens": len(aliases)},
            thread_id="thread-control",
            events=events,
        ),
        stderr="",
        final_message=message,
        tool_logs=[],
        request_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        event_stream_sha256=hashlib.sha256(
            json.dumps(events, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest(),
        tool_logs_sha256=hashlib.sha256(b"[]").hexdigest(),
    )


def test_control_identity_keeps_old_method_budgets_at_luna_max():
    assert MODEL_ID == "gpt-5.6-luna"
    assert REASONING_EFFORT == "max"
    assert set(CONTROL_SYSTEMS) == {
        "agent",
        "plain_llm",
        "rag_dense",
        "rag_reranker",
        "oracle_slice",
    }
    assert AGENT_BUDGET.max_tool_calls == 8
    assert BASELINE_BUDGET.max_tool_calls == 0


def test_seal_predetermines_exact_batches_and_rejects_identity_drift(tmp_path: Path):
    rows = _smoke_rows()
    freeze = _freeze(rows)
    sources = {row.instance_id: materialize(row) for row in rows}
    contexts = build_control_contexts("plain_llm", rows=rows, sources=sources)
    seal = build_control_seal(
        freeze=freeze,
        system_id="plain_llm",
        mode="smoke",
        rows=rows,
        sources=sources,
        contexts=contexts,
    )

    assert seal.row_order == freeze.smoke_instance_ids
    assert len(seal.batch_run_keys) == 3
    assert len(set(seal.batch_run_keys)) == 3
    assert seal.batch_run_keys[0] == control_batch_key(
        freeze=freeze,
        system_id="plain_llm",
        mode="smoke",
        row_run_keys=seal.row_run_keys[:5],
    )
    path = tmp_path / "control-seal.json"
    assert ensure_control_seal(path, seal) == canonical_sha256(seal)
    changed = seal.model_copy(update={"batch_size": 4})
    with pytest.raises(RuntimeError, match="seal differs"):
        ensure_control_seal(path, changed)


def test_transient_batch_failures_remain_pending(tmp_path: Path, monkeypatch):
    rows = _smoke_rows()
    freeze = _freeze(rows)
    _patch_environment(monkeypatch)
    calls = 0

    def interrupted(**kwargs):
        nonlocal calls
        assert (tmp_path / "run-freeze.json").exists()
        assert list(tmp_path.glob("smoke/plain_llm/control-seal.json"))
        assert kwargs["reasoning_effort"] == "max"
        calls += 1
        raise RuntimeError("usage limit")

    records, progress = run_config3_control(
        "plain_llm",
        rows=rows,
        mode="smoke",
        freeze=freeze,
        output_dir=tmp_path,
        entailer=LexicalEntailer(),
        execution_function=interrupted,
    )

    assert calls == 3
    assert records == []
    assert progress.status == "IN_PROGRESS"
    assert progress.pending_instance_ids == [row.instance_id for row in rows]
    assert len(progress.interruptions) == 14
    assert not list((tmp_path / "smoke/plain_llm/records").glob("*.json"))


def test_successful_batches_are_immutable_and_resume_without_provider(
    tmp_path: Path,
    monkeypatch,
):
    rows = _smoke_rows()
    freeze = _freeze(rows)
    _patch_environment(monkeypatch)
    calls: list[dict] = []

    def provider(**kwargs):
        calls.append(kwargs)
        execution = _abstained_execution(kwargs["prompt"])
        return execution.model_copy(
            update={
                "request_sha256": expected_codex_request_sha256(
                    prompt=kwargs["prompt"],
                    schema=kwargs["schema"],
                    sources=kwargs["sources"],
                    transport="wsl",
                    codex_binary=kwargs["codex_binary"],
                    runtime_source_sha256=kwargs["runtime_source_sha256"],
                    chatgpt_account_sha256=kwargs["authentication_identity_sha256"],
                    authorized_hunts=kwargs["authorized_hunts"],
                )
            }
        )

    records, progress = run_config3_control(
        "plain_llm",
        rows=rows,
        mode="smoke",
        freeze=freeze,
        output_dir=tmp_path,
        entailer=LexicalEntailer(),
        execution_function=provider,
    )

    assert len(calls) == 3
    assert all(call["model_id"] == MODEL_ID for call in calls)
    assert all(call["reasoning_effort"] == "max" for call in calls)
    assert all(call["authorized_hunts"] == () for call in calls)
    assert all(
        call["timeout_s"] == BASELINE_BUDGET.wall_clock_timeout_s for call in calls
    )
    assert len(records) == 14
    assert all(
        record.abstained and not record.infrastructure_error for record in records
    )
    assert progress.status == "VALID"
    markers = list((tmp_path / "smoke/plain_llm/raw").glob("*/complete"))
    assert len(markers) == 3

    def should_not_run(**_kwargs):
        raise AssertionError("completed immutable batches must be replayed")

    replayed, replay_progress = run_config3_control(
        "plain_llm",
        rows=rows,
        mode="smoke",
        freeze=freeze,
        output_dir=tmp_path,
        entailer=LexicalEntailer(),
        execution_function=should_not_run,
    )

    assert replayed == records
    assert replay_progress.status == "VALID"

    sidecar = next((tmp_path / "smoke/plain_llm/records").glob("*.json"))
    sidecar.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar hash mismatch"):
        run_config3_control(
            "plain_llm",
            rows=rows,
            mode="smoke",
            freeze=freeze,
            output_dir=tmp_path,
            entailer=LexicalEntailer(),
            execution_function=should_not_run,
        )


def test_runner_refuses_a_test_pilot_before_any_provider_call(tmp_path: Path):
    rows = _smoke_rows()
    with pytest.raises(ValueError, match="no test pilot"):
        run_config3_control(
            "plain_llm",
            rows=rows,
            mode="pilot",  # type: ignore[arg-type]
            freeze=_freeze(rows),
            output_dir=tmp_path,
        )
