from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import scripts.run_t6_independent_review as runner
from cobol_archaeologist.eval.codex_batch import (
    CodexUsage,
    ParsedCodexEvents,
    strict_codex_schema,
)
from cobol_archaeologist.eval.codex_live import CodexTaskExecution
from cobol_archaeologist.eval.config3_live import (
    canonical_sha256,
    expected_codex_request_sha256,
    load_execution_bundle,
    runtime_source_sha256,
)
from scripts.t6_review_coordinator import finalize, initialize

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/benchmark/t6-v2/manifest.json"
ACCOUNT_SHA = "a" * 64
REVIEWER = "model_independent_verifier;model=gpt-5.6-luna;reasoning=max;fresh-pass=v2"
AI_REVIEWER = "model_ai_primary;model=gpt-5.6-sol;reasoning=max;fresh-pass=v1"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "verifier-workspace"
    initialize(
        root=ROOT,
        manifest_path=MANIFEST,
        workspace=workspace,
        reviewer_pseudonym=REVIEWER,
        review_role="independent_verifier",
    )
    return workspace


def _ai_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ai-primary-workspace"
    initialize(
        root=ROOT,
        manifest_path=MANIFEST,
        workspace=workspace,
        reviewer_pseudonym=AI_REVIEWER,
        review_role="ai_primary",
    )
    return workspace


def _response() -> str:
    return json.dumps(
        {
            "decision": "include",
            "drift_type": "D7_conformant",
            "line_level": [],
            "rationale": "The visible source conforms to this authority.",
            "uncertainty_notes": None,
        }
    )


def _execution(
    kwargs: dict[str, object],
    final_message: str,
    *,
    transport: str = "native",
) -> CodexTaskExecution:
    request_sha = expected_codex_request_sha256(
        prompt=str(kwargs["prompt"]),
        schema=kwargs["schema"],
        sources={},
        transport=transport,
        codex_binary=str(kwargs["codex_binary"]),
        runtime_source_sha256=str(kwargs["runtime_source_sha256"]),
        chatgpt_account_sha256=str(kwargs["authentication_identity_sha256"]),
        authorized_hunts=(),
    )
    events = [
        {"type": "thread.started", "thread_id": "fresh-thread"},
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": final_message},
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    ]
    return CodexTaskExecution(
        task_root="ephemeral-task",
        parsed=ParsedCodexEvents(
            final_message=final_message,
            usage=CodexUsage(input_tokens=10, output_tokens=5),
            thread_id="fresh-thread",
            events=events,
        ),
        stderr="",
        final_message=final_message,
        tool_logs=[],
        request_sha256=request_sha,
        event_stream_sha256=canonical_sha256(events),
        tool_logs_sha256=canonical_sha256([]),
    )


def _run(
    *,
    workspace: Path,
    audit_dir: Path,
    execution_function,
    **updates,
):
    kwargs = {
        "root": ROOT,
        "workspace": workspace,
        "audit_dir": audit_dir,
        "transport": "native",
        "codex_binary": "codex.exe",
        "distro": "native-windows",
        "chatgpt_account_sha256": ACCOUNT_SHA,
        "runtime_sha256": runtime_source_sha256(ROOT),
        "max_items": 1,
        "execution_function": execution_function,
        "account_verifier": lambda: ACCOUNT_SHA,
        "now": lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    }
    kwargs.update(updates)
    return runner.run_independent_review(**kwargs)


def test_dry_run_releases_one_item_but_never_calls_provider(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"

    summary = _run(
        workspace=workspace,
        audit_dir=audit_dir,
        execution_function=lambda **_: pytest.fail("provider called during dry run"),
        dry_run=True,
    )

    assert summary.dry_run
    assert summary.provider_calls == 0
    assert summary.pending_review_item_id
    assert (workspace / "current-item.json").is_file()
    identities = list((audit_dir / "requests").glob("*.json"))
    assert len(identities) == 1
    identity = json.loads(identities[0].read_text(encoding="utf-8"))
    assert identity["visible_review_items"] == 1
    assert identity["staged_source_bundles"] == 0
    assert identity["tools_authorized"] == 0
    assert identity["prior_item_context_included"] is False
    assert not (audit_dir / "raw").exists()


def test_runner_uses_fresh_ephemeral_luna_max_without_sources_or_tools(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"
    calls: list[dict[str, object]] = []

    def fake_execution(**kwargs):
        calls.append(kwargs)
        return _execution(kwargs, _response())

    summary = _run(
        workspace=workspace,
        audit_dir=audit_dir,
        execution_function=fake_execution,
    )

    assert summary.completed_items == 1
    assert summary.provider_calls == 1
    assert len(calls) == 1
    call = calls[0]
    assert call["model_id"] == "gpt-5.6-luna"
    assert call["reasoning_effort"] == "max"
    assert call["sources"] == {}
    assert call["authorized_hunts"] == ()
    assert "prior responses" in call["prompt"]
    assert call["schema"]["additionalProperties"] is False
    assert call["schema"] == strict_codex_schema(runner.ReviewResponse)
    assert not (workspace / "current-item.json").exists()
    response = json.loads((workspace / "responses.jsonl").read_text(encoding="utf-8"))
    assert response["reviewer_pseudonym"] == REVIEWER
    assert response["completed_at"] == "2026-08-24T12:00:00Z"
    identity = json.loads(
        next((audit_dir / "requests").glob("*.json")).read_text(encoding="utf-8")
    )
    bundle = load_execution_bundle(
        artifact_dir=audit_dir,
        key=identity["expected_request_sha256"],
        expected_request_sha256=identity["expected_request_sha256"],
    )
    assert bundle is not None
    assert bundle.parsed.events


def test_runner_uses_explicit_nonhuman_sol_max_ai_primary_role(
    tmp_path: Path,
) -> None:
    workspace = _ai_workspace(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_execution(**kwargs):
        calls.append(kwargs)
        return _execution(kwargs, _response())

    summary = _run(
        workspace=workspace,
        audit_dir=tmp_path / "ai-primary-private-audit",
        execution_function=fake_execution,
        review_role="ai_primary",
    )

    assert summary.completed_items == 1
    assert calls[0]["model_id"] == "gpt-5.6-sol"
    assert calls[0]["reasoning_effort"] == "max"
    assert calls[0]["sources"] == {}
    assert "ai_primary reviewer" in str(calls[0]["prompt"])
    response = json.loads((workspace / "responses.jsonl").read_text(encoding="utf-8"))
    assert response["reviewer_pseudonym"] == AI_REVIEWER
    identity = json.loads(
        next(
            (tmp_path / "ai-primary-private-audit" / "requests").glob("*.json")
        ).read_text(encoding="utf-8")
    )
    assert identity["review_role"] == "ai_primary"
    assert identity["model_id"] == "gpt-5.6-sol"


def test_runner_retries_invalid_schema_with_a_new_context_free_task(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"
    prompts: list[str] = []

    def fake_execution(**kwargs):
        prompts.append(kwargs["prompt"])
        final = "{}" if len(prompts) == 1 else _response()
        return _execution(kwargs, final)

    summary = _run(
        workspace=workspace,
        audit_dir=audit_dir,
        execution_function=fake_execution,
    )

    assert summary.provider_calls == 2
    assert summary.invalid_attempts == 1
    assert len(prompts) == 2
    assert "Fresh isolated attempt: 1" in prompts[0]
    assert "Fresh isolated attempt: 2" in prompts[1]
    assert _response() not in prompts[1]
    assert len(list((audit_dir / "invalid").glob("*.json"))) == 1
    assert len(list((audit_dir / "raw").glob("*"))) == 2


def test_account_identity_is_rechecked_before_every_provider_call(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"
    provider_calls = 0
    identities = iter([ACCOUNT_SHA, ACCOUNT_SHA, "b" * 64])

    def fake_execution(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return _execution(kwargs, "{}")

    with pytest.raises(RuntimeError, match="differs from frozen identity"):
        _run(
            workspace=workspace,
            audit_dir=audit_dir,
            execution_function=fake_execution,
            account_verifier=lambda: next(identities),
        )
    assert provider_calls == 1


def test_complete_run_freezes_22_item_aggregate_and_metadata_pin(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"

    def fake_execution(**kwargs):
        return _execution(kwargs, _response())

    summary = _run(
        workspace=workspace,
        audit_dir=audit_dir,
        execution_function=fake_execution,
        max_items=22,
    )

    assert summary.completed_items == 22
    assert summary.provider_calls == 22
    assert summary.audit_manifest is not None
    aggregate = json.loads(
        (ROOT / summary.audit_manifest.path).read_text(encoding="utf-8")
    )
    assert aggregate["release_ordinal_order"] == list(range(1, 23))
    assert len(aggregate["items"]) == 22
    assert all(len(item["attempts"]) == 1 for item in aggregate["items"])
    metadata_path = tmp_path / "verifier-metadata.json"
    finalize(
        root=ROOT,
        workspace=workspace,
        metadata_path=metadata_path,
        independent_verifier_audit_manifest=summary.audit_manifest,
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["controlled_model_audit_manifest"] == (
        summary.audit_manifest.model_dump(mode="json")
    )


def test_runner_resumes_persisted_raw_bundle_without_second_provider_call(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"
    calls = 0

    def fake_execution(**kwargs):
        nonlocal calls
        calls += 1
        return _execution(kwargs, _response())

    original = runner.record_response
    monkeypatch.setattr(
        runner,
        "record_response",
        lambda **_: (_ for _ in ()).throw(RuntimeError("simulated crash")),
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        _run(
            workspace=workspace,
            audit_dir=audit_dir,
            execution_function=fake_execution,
        )
    assert calls == 1
    assert (workspace / "current-item.json").is_file()

    monkeypatch.setattr(runner, "record_response", original)
    summary = _run(
        workspace=workspace,
        audit_dir=audit_dir,
        execution_function=lambda **_: pytest.fail("provider called on resume"),
    )
    assert summary.completed_items == 1
    assert summary.provider_calls == 0
    assert not (workspace / "current-item.json").exists()


def test_runner_refuses_wrong_chatgpt_account_before_release(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(RuntimeError, match="differs from frozen identity"):
        _run(
            workspace=workspace,
            audit_dir=tmp_path / "private-audit",
            execution_function=lambda **_: pytest.fail("provider called"),
            account_verifier=lambda: "b" * 64,
        )
    assert not (workspace / "current-item.json").exists()


def test_runner_refuses_private_audit_history_inside_reviewer_workspace(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError, match="must be separate"):
        _run(
            workspace=workspace,
            audit_dir=workspace / "audit",
            execution_function=lambda **_: pytest.fail("provider called"),
            dry_run=True,
        )


def test_wsl_runner_uses_prepared_frozen_support_runtime(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"
    prepared: list[dict[str, str]] = []
    calls: list[dict[str, object]] = []

    def prepare(**kwargs):
        prepared.append(kwargs)
        return "/tmp/frozen-support-runtime"

    def fake_execution(**kwargs):
        calls.append(kwargs)
        return _execution(kwargs, _response(), transport="wsl")

    summary = _run(
        workspace=workspace,
        audit_dir=audit_dir,
        execution_function=fake_execution,
        transport="wsl",
        distro="Ubuntu",
        codex_binary="/mnt/c/codex.exe",
        support_runtime_preparer=prepare,
    )

    assert summary.completed_items == 1
    assert prepared == [{"commit": runtime_source_sha256(ROOT), "distro": "Ubuntu"}]
    assert calls[0]["support_root"] == "/tmp/frozen-support-runtime"


def test_aggregate_rejects_post_accepted_attempt_identity(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    audit_dir = tmp_path / "private-audit"
    calls = 0

    def fake_execution(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 22:
            first_path = min((audit_dir / "requests").glob("*.json"))
            identity = json.loads(first_path.read_text(encoding="utf-8"))
            identity["attempt"] = 2
            extra_path = runner._identity_path(audit_dir, identity["review_item_id"], 2)
            extra_path.write_text(json.dumps(identity), encoding="utf-8")
        return _execution(kwargs, _response())

    with pytest.raises(ValueError, match="orphan, gapped, or post-accepted"):
        _run(
            workspace=workspace,
            audit_dir=audit_dir,
            execution_function=fake_execution,
            max_items=22,
        )
