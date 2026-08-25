from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cobol_archaeologist.eval.codex_tool import ToolRequest
from cobol_archaeologist.eval.collaboration_staging import (
    TOOL_LOG_NAME,
    execute_staged_tool_request,
    load_staged_tool_logs,
    load_staged_tool_records,
    stage_collaboration_task,
    tool_log_entry_sha256,
)
from cobol_archaeologist.eval.materialize import MaterializedSource


def _source(text: str, *, filename: str = "CASE.cbl") -> MaterializedSource:
    return MaterializedSource(
        main_file=filename,
        files={filename: text},
        source_sha256=(text.encode().hex() + "0" * 64)[:64],
    )


def _request(
    *, alias: str = "drift_900000", hunt: str = "D1_stale_threshold"
) -> ToolRequest:
    return ToolRequest(
        alias=alias,
        hunt=hunt,
        tool="read_program",
        arguments={"program": "CASE"},
    )


class _FakeTools:
    def __init__(self, source: Path):
        self.source = source

    def read_program(self, program: str):
        return {
            "program": program,
            "source": (self.source / "CASE.cbl").read_text(encoding="utf-8"),
        }


def _execute(task, staging_base: Path, request: ToolRequest | None = None):
    return execute_staged_tool_request(
        request or _request(),
        staging_base=staging_base,
        run_key=task.run_key,
        expected_staging_sha256=task.staging_sha256,
        tool_factory=_FakeTools,
    )


def test_staging_is_deterministic_and_command_is_task_keyed(tmp_path: Path) -> None:
    run_key = "a" * 64
    first = stage_collaboration_task(
        staging_base=tmp_path / "one",
        run_key=run_key,
        sources={"drift_900000": _source("ONE\n")},
        authorized_hunts=("D1_stale_threshold",),
    )
    second = stage_collaboration_task(
        staging_base=tmp_path / "two",
        run_key=run_key,
        sources={"drift_900000": _source("ONE\n")},
        authorized_hunts=("D1_stale_threshold",),
    )

    assert first.staging_sha256 == second.staging_sha256
    assert first.task_root.name == second.task_root.name == run_key
    assert run_key in first.tool_command
    assert first.staging_sha256 in first.tool_command
    assert (first.task_root / "cases/drift_900000/CASE.cbl").read_bytes() == b"ONE\n"
    assert (first.task_root / "descriptor.json").read_bytes() == (
        second.task_root / "descriptor.json"
    ).read_bytes()


def test_identical_resume_succeeds_and_nonidentical_resume_fails_closed(
    tmp_path: Path,
) -> None:
    run_key = "b" * 64
    arguments = {
        "staging_base": tmp_path,
        "run_key": run_key,
        "sources": {"drift_900000": _source("ORIGINAL\n")},
        "authorized_hunts": ("D1_stale_threshold",),
    }
    first = stage_collaboration_task(**arguments)
    assert stage_collaboration_task(**arguments) == first

    with pytest.raises(RuntimeError, match="manifest is nonidentical"):
        stage_collaboration_task(
            **{**arguments, "sources": {"drift_900000": _source("CHANGED\n")}}
        )


def test_parallel_tasks_isolate_the_same_opaque_alias(tmp_path: Path) -> None:
    first = stage_collaboration_task(
        staging_base=tmp_path,
        run_key="c" * 64,
        sources={"drift_900000": _source("FIRST\n")},
        authorized_hunts=("D1_stale_threshold",),
    )
    second = stage_collaboration_task(
        staging_base=tmp_path,
        run_key="d" * 64,
        sources={"drift_900000": _source("SECOND\n")},
        authorized_hunts=("D1_stale_threshold",),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda task: _execute(task, tmp_path), (first, second)))

    assert records[0].entry.sequence == records[1].entry.sequence == 1
    assert "FIRST" in records[0].entry.observation_summary
    assert "SECOND" in records[1].entry.observation_summary
    assert first.task_root != second.task_root


def test_tool_log_sequence_and_hash_chain_are_host_verifiable(tmp_path: Path) -> None:
    task = stage_collaboration_task(
        staging_base=tmp_path,
        run_key="e" * 64,
        sources={"drift_900000": _source("SOURCE\n")},
        authorized_hunts=("D1_stale_threshold",),
    )
    _execute(task, tmp_path)
    _execute(task, tmp_path)

    records = load_staged_tool_records(
        staging_base=tmp_path,
        run_key=task.run_key,
        expected_staging_sha256=task.staging_sha256,
    )
    logs = load_staged_tool_logs(
        staging_base=tmp_path,
        run_key=task.run_key,
        expected_staging_sha256=task.staging_sha256,
    )

    assert [row.sequence for row in records] == [1, 2]
    assert [row.sequence for row in logs] == [1, 2]
    assert records[0].previous_sha256 == "0" * 64
    assert records[1].previous_sha256 == records[0].record_sha256
    assert tool_log_entry_sha256(logs[0]) == tool_log_entry_sha256(records[0].entry)


def test_unauthorized_hunt_and_alias_never_reach_tool_layer(tmp_path: Path) -> None:
    task = stage_collaboration_task(
        staging_base=tmp_path,
        run_key="f" * 64,
        sources={"drift_900000": _source("SOURCE\n")},
        authorized_hunts=("D1_stale_threshold",),
    )

    with pytest.raises(ValueError, match="unauthorized collaboration hunt"):
        _execute(task, tmp_path, _request(hunt="D2_missing_rule"))
    with pytest.raises(ValueError, match="unauthorized collaboration alias"):
        _execute(task, tmp_path, _request(alias="drift_900001"))
    assert not (task.task_root / TOOL_LOG_NAME).exists()


def test_staging_and_log_tampering_fail_closed(tmp_path: Path) -> None:
    stage_base = tmp_path / "source-tamper"
    task = stage_collaboration_task(
        staging_base=stage_base,
        run_key="1" * 64,
        sources={"drift_900000": _source("SOURCE\n")},
        authorized_hunts=("D1_stale_threshold",),
    )
    (task.task_root / "cases/drift_900000/CASE.cbl").write_text(
        "TAMPERED\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="byte mismatch"):
        _execute(task, stage_base)

    log_base = tmp_path / "log-tamper"
    logged = stage_collaboration_task(
        staging_base=log_base,
        run_key="2" * 64,
        sources={"drift_900000": _source("SOURCE\n")},
        authorized_hunts=("D1_stale_threshold",),
    )
    _execute(logged, log_base)
    log_path = logged.task_root / TOOL_LOG_NAME
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    payload["entry"]["observation_summary"] = "tampered"
    log_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record hash"):
        load_staged_tool_records(
            staging_base=log_base,
            run_key=logged.run_key,
            expected_staging_sha256=logged.staging_sha256,
        )


@pytest.mark.parametrize("filename", ["../escape.cbl", "/escape.cbl", "..\\escape.cbl"])
def test_staging_rejects_source_path_escape(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ValueError, match="unsafe staged relative path"):
        stage_collaboration_task(
            staging_base=tmp_path,
            run_key="3" * 64,
            sources={"drift_900000": _source("SOURCE\n", filename=filename)},
            authorized_hunts=("adaptive",),
        )
