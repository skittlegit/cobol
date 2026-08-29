"""Offline gates for the frozen configuration-3 Luna/max runner."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from cobol_archaeologist.agent.loop import _summarize
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.eval.codex_batch import (
    ParsedCodexEvents,
    SubmittedResponse,
    strict_codex_schema,
)
from cobol_archaeologist.eval.codex_live import CodexTaskExecution
from cobol_archaeologist.eval.codex_tool import ToolLogEntry
from cobol_archaeologist.eval.config3_live import (
    ADAPTIVE_BATCH_SIZE,
    CONFIG3_AGENT_BUDGET,
    CONFIG3_SMOKE_SEED,
    CONFIG3_SYSTEMS,
    MODEL_ID,
    PHASE5_AGGREGATE_PATHS,
    PHASE5_BASELINE_PATHS,
    REASONING_EFFORT,
    CodexAdaptiveEnvelope,
    Config3InterproceduralComparison,
    Config3Progress,
    Config3QualityMetrics,
    Config3RunFreeze,
    Config3TemporalScore,
    DevelopmentSmokeFreeze,
    FinalizedArtifactPin,
    SubmittedAdaptiveCase,
    TemporalPairScore,
    _validate_finalized_pin,
    bounded_provider_map,
    build_adaptive_codex_prompt,
    build_config3_freeze,
    canonical_sha256,
    config3_run_key,
    ensure_frozen_identity,
    finalize_adaptive_case,
    load_execution_bundle,
    load_finalized_t6_rows,
    persist_execution_bundle,
    refresh_smoke_readiness,
    require_full_smoke_readiness,
    run_config3_adaptive,
    runtime_source_sha256,
    seeded_dev_smoke,
)
from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.model.prompt import AgentResponse, EvidenceLedgerNote
from cobol_archaeologist.model.verify import LexicalEntailer
from cobol_archaeologist.schemas import DriftInstance, RegulationClause

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "tests" / "fixtures" / "hunts"
CACHE = FIX / "cached_decisions.json"
CORPUS = FIX / "corpus"


def _rows(case: str) -> list[dict]:
    return json.loads(CACHE.read_text(encoding="utf-8"))[case]


def test_finalized_text_pin_accepts_lf_checkout_of_legacy_crlf_hash(
    tmp_path: Path,
):
    artifact = tmp_path / "evidence.json"
    artifact.write_bytes(b'{\n  "status": "sealed"\n}\n')
    legacy_crlf = artifact.read_bytes().replace(b"\n", b"\r\n")
    pin = FinalizedArtifactPin(
        path="evidence.json",
        sha256=hashlib.sha256(legacy_crlf).hexdigest(),
    )

    assert _validate_finalized_pin(tmp_path.resolve(), pin) == artifact.resolve()

    artifact.write_bytes(b'{\n  "status": "changed"\n}\n')
    with pytest.raises(ValueError, match="finalized T6 artifact pin changed"):
        _validate_finalized_pin(tmp_path.resolve(), pin)


def _provider_response(response: AgentResponse) -> SubmittedResponse:
    payload = response.model_dump(mode="json")
    prediction = payload["prediction"]
    payload["prediction"] = {
        key: value
        for key, value in prediction.items()
        if key not in {"instance_id", "regulation_clause"}
    }
    for key in (
        "tool",
        "arguments",
            "token_count",
            "token_count_recorded",
            "raw_provider_text",
        "contract_error",
        "evidence_ledger",
    ):
        payload.pop(key, None)
    return SubmittedResponse.model_validate(payload)


def _d5_submission():
    tool_turn = AgentResponse.model_validate(_rows("d5")[0])
    final = AgentResponse.model_validate(_rows("d5")[-1])
    tools = StubToolLayer(CORPUS)
    observation = getattr(tools, tool_turn.tool)(**tool_turn.arguments)
    summary, truncated = _summarize(observation)
    log = ToolLogEntry(
        alias="drift_900000",
        hunt="adaptive",
        sequence=1,
        tool=tool_turn.tool,
        arguments=tool_turn.arguments,
        observation_summary=summary,
        observation_truncated=truncated,
        error=None,
        latency_ms=0,
    )
    note = EvidenceLedgerNote(
        observation_step=1,
        observation_sha256=hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        hypothesis="D5_boundary_error",
        bearing="supports",
        rationale="The observed comparator supports the D5 boundary hypothesis.",
    )
    clause = RegulationClause.model_validate(
        final.prediction.regulation_clause.model_dump()
    )
    return (
        SubmittedAdaptiveCase(
            alias="drift_900000",
            evidence_ledger=[note],
            response=_provider_response(final),
        ),
        clause,
        log,
        tools,
    )


def _freeze(**updates) -> Config3RunFreeze:
    payload = {
        "provider": "chatgpt-codex",
        "authentication": "ChatGPT",
        "prompt_version": "m4-config3-adaptive-v1",
        "repository_commit": "a" * 40,
        "runtime_source_sha256": runtime_source_sha256(ROOT),
        "codex_cli_version": "codex 1.2.3",
        "wsl_distribution": "Ubuntu",
        "transport": "wsl",
        "codex_binary": "/home/deepa/.local/bin/codex-x86_64-unknown-linux-musl",
        "max_workers": 3,
        "systems": CONFIG3_SYSTEMS,
        "budgets": {"adaptive_agent": CONFIG3_AGENT_BUDGET.model_dump(mode="json")},
        "batch_sizes": {"adaptive_agent": 1},
        "identity_hashes": {"prompt": "b" * 64},
        "phase5_baseline_sha256": {
            path.as_posix(): hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in PHASE5_BASELINE_PATHS
        },
        "phase5_aggregate_sha256": {
            path.as_posix(): hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in PHASE5_AGGREGATE_PATHS
        },
        "chatgpt_account_sha256": "9" * 64,
        "dev_split_path": "data/benchmark/v1/dev.jsonl",
        "dev_split_sha256": "c" * 64,
        "train_split_path": "data/benchmark/v1/train.jsonl",
        "train_split_sha256": "1" * 64,
        "test_split_path": "data/benchmark/v1/test.jsonl",
        "test_split_sha256": "d" * 64,
        "t6_v2_path": "data/benchmark/t6-v2/pairs.jsonl",
        "t6_v2_sha256": "e" * 64,
        "smoke_seed": CONFIG3_SMOKE_SEED,
        "smoke_instance_ids": tuple(f"drift_{index:06d}" for index in range(14)),
        "dev_order": ("dev-1",),
        "test_order": ("test-1",),
        "t6_order": ("t6-1",),
        "t6_source_inputs": {},
        "source_sha256": {"dev-1": "f" * 64},
    }
    payload.update(updates)
    return Config3RunFreeze.model_validate(payload)


def test_provider_identity_and_candidate_batch_are_frozen():
    assert MODEL_ID == "gpt-5.6-luna"
    assert REASONING_EFFORT == "max"
    assert ADAPTIVE_BATCH_SIZE == 1
    assert CONFIG3_AGENT_BUDGET.max_tool_calls == 16


def test_official_freeze_consumes_finalized_t6_roster():
    freeze = build_config3_freeze(
        repository_commit_value="a" * 40,
        transport="collaboration_subagent",
    )

    assert freeze.t6_v2_path == "data/benchmark/t6-v2/final/manifest.json"
    assert len(freeze.t6_order) == 40
    assert len(freeze.t6_source_inputs) == 40


def test_finalized_t6_protocol_requires_40_side_rows_and_pinned_sources(
    tmp_path: Path,
) -> None:
    test_rows = [
        DriftInstance.model_validate_json(line)
        for line in (ROOT / "data/benchmark/v1/test.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    by_id = {row.instance_id: row for row in test_rows}
    pair = [by_id["drift_000007"], by_id["drift_000008"]]
    source_from = ROOT / "data/benchmark/seed/programs/BOIDENT1.cbl"
    source_to = tmp_path / "sources/BOIDENT1.cbl"
    source_to.parent.mkdir(parents=True)
    source_to.write_bytes(source_from.read_bytes())
    rows = [
        row.model_copy(update={"instance_id": f"drift_{120000 + index:06d}"})
        for index in range(40)
        for row in [pair[index % 2]]
    ]
    rows_path = tmp_path / "evaluation-rows.jsonl"
    rows_path.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8"
    )
    source_pin = {
        "path": "sources/BOIDENT1.cbl",
        "sha256": hashlib.sha256(source_to.read_bytes()).hexdigest(),
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "finalized": True,
                "evaluation_ready": True,
                "target_pair_count": 20,
                "evaluation_side_count": 40,
                "pair_order": [f"pair-{index:02d}" for index in range(20)],
                "instance_order": [row.instance_id for row in rows],
                "evaluation_rows": {
                    "path": "evaluation-rows.jsonl",
                    "sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
                },
                "source_inputs": {row.instance_id: source_pin for row in rows},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="pair_members"):
        load_finalized_t6_rows(root=tmp_path, manifest_path=manifest_path)


def test_prompt_contains_one_opaque_case_and_no_gold_identity():
    submitted, clause, *_ = _d5_submission()
    prompt = build_adaptive_codex_prompt(
        alias=submitted.alias,
        clause=clause,
        program_scope="LIMIT1",
        tool_command="/support/python -m cobol_archaeologist.eval.codex_tool",
    )

    assert prompt.count('"alias":"drift_900000"') == 1
    assert " adaptive TOOL " in prompt
    assert "drift_910005" not in prompt
    assert "gold_rationale" not in prompt
    assert "mutation provenance" in prompt
    assert str(CACHE) not in prompt
    assert "claim` is the clause-grounded regulatory proposition" in prompt
    schema = strict_codex_schema(CodexAdaptiveEnvelope)
    claim = schema["$defs"]["SubmittedResponse"]["properties"]["claim"]
    assert "never a COBOL implementation" in claim["description"]


def test_adaptive_wire_contract_rejects_more_than_one_case():
    submitted, *_ = _d5_submission()
    CodexAdaptiveEnvelope(results=[submitted])
    with pytest.raises(ValidationError):
        CodexAdaptiveEnvelope(results=[submitted, submitted])


def test_host_finalizer_binds_inputs_and_uses_unchanged_verifier():
    submitted, clause, log, tools = _d5_submission()
    outcome = finalize_adaptive_case(
        submitted,
        clause=clause,
        program_scope="LIMIT1",
        instance_id="drift_910005",
        logs=[log],
        tools=tools,
        entailer=LexicalEntailer(),
        token_count=100,
    )

    assert not outcome.abstained
    assert outcome.finding.instance_id == "drift_910005"
    assert outcome.finding.regulation_clause == clause
    assert outcome.verification.verified
    assert outcome.evidence_ledger == submitted.evidence_ledger


def test_host_finalizer_marks_unavailable_token_usage_without_resource_claim():
    submitted, clause, log, tools = _d5_submission()
    outcome = finalize_adaptive_case(
        submitted,
        clause=clause,
        program_scope="LIMIT1",
        instance_id="drift_910005",
        logs=[log],
        tools=tools,
        entailer=LexicalEntailer(),
        token_count=0,
        token_count_recorded=False,
    )

    assert not outcome.abstained
    assert outcome.trajectory.tokens_used == 0
    assert outcome.trajectory.token_usage_recorded is False
    assert outcome.trajectory.model_responses[0].token_count_recorded is False


def test_corrupt_model_ledger_hash_fails_closed_before_emission():
    submitted, clause, log, tools = _d5_submission()
    bad_note = submitted.evidence_ledger[0].model_copy(
        update={"observation_sha256": "0" * 64}
    )
    submitted = submitted.model_copy(update={"evidence_ledger": [bad_note]})

    outcome = finalize_adaptive_case(
        submitted,
        clause=clause,
        program_scope="LIMIT1",
        instance_id="drift_910005",
        logs=[log],
        tools=tools,
        entailer=LexicalEntailer(),
        token_count=100,
    )

    assert outcome.abstained
    assert outcome.finding is None
    assert "observation hash differs" in outcome.abstention_reason


def test_dev_smoke_is_two_per_class_and_never_uses_test_rows():
    dev = [
        DriftInstance.model_validate_json(line)
        for line in (ROOT / "data/benchmark/v1/dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    train = [
        DriftInstance.model_validate_json(line)
        for line in (ROOT / "data/benchmark/v1/train.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    test_ids = {
        json.loads(line)["instance_id"]
        for line in (ROOT / "data/benchmark/v1/test.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    selected = seeded_dev_smoke(dev, fallback_rows=train)

    assert len(selected) == 14
    assert [row.instance_id for row in selected] == [
        row.instance_id for row in seeded_dev_smoke(dev, fallback_rows=train)
    ]
    assert not ({row.instance_id for row in selected} & test_ids)
    assert {
        drift_type: sum(row.drift_type == drift_type for row in selected)
        for drift_type in {row.drift_type for row in selected}
    } == {drift_type: 2 for drift_type in {row.drift_type for row in selected}}
    committed = DevelopmentSmokeFreeze.model_validate_json(
        (ROOT / "data/eval/legacy/m4-config3/development-smoke.json").read_text(
            encoding="utf-8"
        )
    )
    committed_ids = {row.instance_id for row in committed.rows}
    assert len(committed.rows) == 14
    assert not (committed_ids & test_ids)
    assert {
        drift_type: sum(row.drift_type == drift_type for row in committed.rows)
        for drift_type in {row.drift_type for row in committed.rows}
    } == {drift_type: 2 for drift_type in {row.drift_type for row in committed.rows}}
    assert committed.hidden_test_rows == 0


def test_run_key_binds_the_complete_freeze_identity():
    freeze = _freeze()
    key = config3_run_key(
        freeze=freeze,
        system_id="adaptive_agent",
        run_mode="smoke",
        instance_id="dev-1",
        source_sha256="f" * 64,
    )
    changed = config3_run_key(
        freeze=_freeze(max_workers=2),
        system_id="adaptive_agent",
        run_mode="smoke",
        instance_id="dev-1",
        source_sha256="f" * 64,
    )

    assert len(key) == 64
    assert key != changed
    assert canonical_sha256(freeze) == canonical_sha256(_freeze())


def test_temporal_score_rejects_reordered_or_reused_pair_members() -> None:
    pairs = tuple(
        TemporalPairScore(
            pair_id=f"pair-{index:02d}",
            instance_ids=(f"side-{2 * index:02d}", f"side-{2 * index + 1:02d}"),
            authority_target="grievance_response_deadline",
            side_correct=(True, True),
            pair_correct=True,
        )
        for index in range(20)
    )
    payload = {
        "freeze_sha256": "1" * 64,
        "finalized_t6_sha256": "2" * 64,
        "records_sha256": "3" * 64,
        "pair_order": tuple(pair.pair_id for pair in pairs),
        "pairs": pairs,
        "paired_correct": 20,
        "paired_accuracy": 1.0,
    }
    assert Config3TemporalScore.model_validate(payload).paired_accuracy == 1.0
    payload["pair_order"] = tuple(reversed(payload["pair_order"]))
    with pytest.raises(ValidationError, match="pinned pair_order"):
        Config3TemporalScore.model_validate(payload)
    payload["pair_order"] = tuple(pair.pair_id for pair in pairs)
    reused = pairs[1].model_copy(update={"instance_ids": pairs[0].instance_ids})
    payload["pairs"] = (pairs[0], reused, *pairs[2:])
    with pytest.raises(ValidationError, match="40 unique"):
        Config3TemporalScore.model_validate(payload)


def test_quality_model_requires_all_predeclared_gate_results() -> None:
    comparison = Config3InterproceduralComparison(
        paired_rows=36,
        adaptive_f1=0.8,
        rag_reranker_f1=0.6,
        delta_f1=0.2,
        bootstrap_95_ci=(0.05, 0.3),
        paired_randomization_p=0.01,
    )
    gates = {
        "t1_f1": True,
        "balanced_accuracy": True,
        "answer_rate": True,
        "answered_accuracy": True,
        "interprocedural_advantage": True,
        "temporal_paired_accuracy": True,
        "verified_evidence": True,
    }
    payload = {
        "freeze_sha256": "1" * 64,
        "adaptive_records_sha256": "2" * 64,
        "rag_reranker_records_sha256": "3" * 64,
        "temporal_score_sha256": "4" * 64,
        "evidence_policy_sha256": "5" * 64,
        "verifier_sha256": "6" * 64,
        "bootstrap_resamples": 10_000,
        "randomization_samples": 20_000,
        "statistics_seed": 20_260_823,
        "t1_f1": 0.8,
        "balanced_accuracy": 0.7,
        "answer_rate": 0.7,
        "answered_accuracy": 0.9,
        "interprocedural": comparison,
        "temporal_pair_count": 20,
        "temporal_paired_accuracy": 0.75,
        "unverified_emissions": 0,
        "evidence_threshold_relaxed": False,
        "gates": gates,
        "all_gates_pass": True,
    }
    assert Config3QualityMetrics.model_validate(payload).all_gates_pass
    payload["t1_f1"] = 0.69
    with pytest.raises(ValidationError, match="gate results are inconsistent"):
        Config3QualityMetrics.model_validate(payload)


def test_bounded_provider_map_runs_concurrently_within_exact_cap():
    active = maximum = 0
    lock = threading.Lock()

    def worker(value: int) -> int:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return value * 2

    completions = list(bounded_provider_map(list(range(8)), worker, max_workers=3))

    assert maximum == 3
    assert {item: result for item, result, error in completions if error is None} == {
        value: value * 2 for value in range(8)
    }


def test_raw_execution_bundle_is_hash_checked_and_resumable(tmp_path: Path):
    events = [{"type": "turn.completed"}]
    execution = CodexTaskExecution(
        task_root="/task/one",
        parsed=ParsedCodexEvents(
            final_message='{"results":[]}',
            usage={},
            thread_id="thread-1",
            events=events,
        ),
        stderr="",
        final_message='{"results":[]}',
        tool_logs=[],
        request_sha256="1" * 64,
        event_stream_sha256=hashlib.sha256(
            json.dumps(events, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest(),
        tool_logs_sha256=hashlib.sha256(b"[]").hexdigest(),
    )
    persist_execution_bundle(execution, artifact_dir=tmp_path, key="a" * 64)

    assert load_execution_bundle(artifact_dir=tmp_path, key="a" * 64) == execution
    marker = tmp_path / "raw" / ("a" * 64) / "complete"
    marker.write_text("0" * 64, encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_execution_bundle(artifact_dir=tmp_path, key="a" * 64)


def test_full_requires_hash_bound_all_six_system_smoke_gate(tmp_path: Path):
    freeze = _freeze()
    with pytest.raises(RuntimeError, match="completed configuration-3 smoke"):
        require_full_smoke_readiness(
            output_dir=tmp_path,
            freeze=freeze,
            system_id="adaptive_agent",
        )
    for system_id in CONFIG3_SYSTEMS:
        path = tmp_path / "smoke" / system_id / "progress.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            Config3Progress(
                freeze_sha256=canonical_sha256(freeze),
                system_id=system_id,
                run_mode="smoke",
                completed_run_keys=[],
                pending_instance_ids=[],
                interruptions={},
                status="VALID",
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
    assert refresh_smoke_readiness(output_dir=tmp_path, freeze=freeze) is None
    with pytest.raises(RuntimeError, match="pinned source hash|exact 14 run keys"):
        require_full_smoke_readiness(
            output_dir=tmp_path,
            freeze=freeze,
            system_id="adaptive_agent",
        )


def test_freeze_is_written_before_any_concurrent_provider_call(
    tmp_path: Path,
    monkeypatch,
):
    dev = [
        DriftInstance.model_validate_json(line)
        for line in (ROOT / "data/benchmark/v1/dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    train = [
        DriftInstance.model_validate_json(line)
        for line in (ROOT / "data/benchmark/v1/train.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    smoke = seeded_dev_smoke(dev, fallback_rows=train)
    source_hashes = {row.instance_id: materialize(row).source_sha256 for row in smoke}
    freeze = _freeze(
        smoke_instance_ids=tuple(row.instance_id for row in smoke),
        dev_order=tuple(row.instance_id for row in dev),
        source_sha256=source_hashes,
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_live.repository_commit",
        lambda _root: "a" * 40,
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_live._check_chatgpt_login",
        lambda **_kwargs: "Logged in using ChatGPT",
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_live._wsl",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=b"codex 1.2.3\n",
            stderr=b"",
        ),
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_live._wsl_chatgpt_account_sha256",
        lambda **_kwargs: "9" * 64,
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_live.prepare_support_runtime",
        lambda **_kwargs: "/support",
    )
    calls = 0

    def interrupted_provider(**_kwargs):
        nonlocal calls
        assert (tmp_path / "run-freeze.json").exists()
        calls += 1
        raise RuntimeError("usage limit")

    records, progress = run_config3_adaptive(
        rows=smoke,
        mode="smoke",
        freeze=freeze,
        output_dir=tmp_path,
        max_workers=3,
        entailer=LexicalEntailer(),
        execution_function=interrupted_provider,
    )

    assert calls == 14
    assert records == []
    assert progress.status == "IN_PROGRESS"
    assert len(progress.pending_instance_ids) == 14
    assert len(progress.interruptions) == 14
    assert ensure_frozen_identity(tmp_path / "run-freeze.json", freeze) == (
        canonical_sha256(freeze)
    )
