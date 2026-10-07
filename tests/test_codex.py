"""Codex transport: event parsing and fail-closed tool-log reconstruction."""

from __future__ import annotations

import json
import shlex

import pytest

from cobol_archaeologist.eval import codex

BRIDGE = "/s/.venv/bin/python -m cobol_archaeologist.eval.bridge"
ALIAS = "drift_900000"


def _command(operation: str, arguments: dict) -> str:
    payload = json.dumps(arguments, separators=(",", ":")).replace('"', '\\"')
    return f"/bin/bash -lc \"{BRIDGE} {ALIAS} {operation} --arguments '{payload}'\""


def _events(*items: dict, final: str = '{"results":[]}') -> codex.ParsedEvents:
    events = [{"type": "thread.started", "thread_id": "t"}]
    for index, item in enumerate(items):
        started = {**item, "id": f"i{index}", "status": "in_progress"}
        started.pop("aggregated_output", None)
        events.append({"type": "item.started", "item": started})
        events.append({"type": "item.completed", "item": {**item, "id": f"i{index}"}})
    events.append(
        {
            "type": "item.completed",
            "item": {"id": "m", "type": "agent_message", "text": final},
        }
    )
    events.append(
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}
    )
    stdout = "\n".join(json.dumps(event) for event in events)
    return codex.parse_events(stdout)


def _tool_item(
    operation: str, arguments: dict, output: dict, exit_code: int = 0
) -> dict:
    return {
        "type": "command_execution",
        "command": _command(operation, arguments),
        "aggregated_output": json.dumps(output),
        "exit_code": exit_code,
        "status": "completed" if exit_code == 0 else "failed",
    }


def test_parse_events_reads_final_message_and_usage():
    parsed = _events(final='{"ok":true}')
    assert parsed.final_message == '{"ok":true}'
    assert parsed.usage.total_tokens == 15


def test_bridge_calls_become_trusted_tool_logs():
    output = {
        "tool": "read_program",
        "sequence": 1,
        "observation_summary": "{}",
        "observation_truncated": False,
        "error": None,
    }
    stream = codex.authorize_events(
        _events(_tool_item("read_program", {"program": "OVDCHK1"}, output)),
        tool_command=BRIDGE,
        aliases=[ALIAS],
    )
    assert len(stream.tool_logs) == 1
    assert stream.tool_logs[0].arguments == {"program": "OVDCHK1"}
    assert stream.rejected_commands == 0


def test_rejected_bridge_calls_are_counted_not_fatal():
    stream = codex.authorize_events(
        _events(
            _tool_item(
                "read_program",
                {"program": "X"},
                {"infrastructure_error": "bad"},
                exit_code=2,
            )
        ),
        tool_command=BRIDGE,
        aliases=[ALIAS],
    )
    assert stream.tool_logs == []
    assert stream.rejected_commands == 1


def test_check_finding_results_are_kept_separate():
    stream = codex.authorize_events(
        _events(
            _tool_item(
                "check_finding",
                {"response": {}},
                {"check": "check_finding", "accepted": False, "rejection": "x"},
            )
        ),
        tool_command=BRIDGE,
        aliases=[ALIAS],
    )
    assert stream.tool_logs == []
    assert stream.checks[0]["accepted"] is False


def test_any_other_command_invalidates_the_task():
    item = {
        "type": "command_execution",
        "command": '/bin/bash -lc "cat /etc/passwd"',
        "aggregated_output": "",
        "exit_code": 0,
        "status": "completed",
    }
    with pytest.raises(ValueError, match="not the tool bridge"):
        codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])


def test_file_changes_invalidate_the_task():
    item = {"type": "file_change", "changes": []}
    with pytest.raises(ValueError, match="unauthorized Codex item type"):
        codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])


def test_unknown_alias_invalidates_the_task():
    item = _tool_item("grep", {"pattern": "X"}, {})
    item["command"] = item["command"].replace(ALIAS, "drift_911111")
    with pytest.raises(ValueError, match="unknown alias"):
        codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])


def test_strict_schema_requires_every_property():
    from cobol_archaeologist.eval.detector import DetectorEnvelope

    schema = codex.strict_schema(DetectorEnvelope)

    def check(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert set(node["required"]) == set(node["properties"])
                assert node["additionalProperties"] is False
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(schema)


def test_method_hash_ignores_reporting_code_but_not_detector_code(monkeypatch):
    files = codex._runtime_files()
    base = codex.method_hash()

    def edited(path: str):
        changed = dict(files)
        changed[path] = files[path] + b"# edit"
        return lambda: changed

    monkeypatch.setattr(
        codex, "_runtime_files", edited("src/cobol_archaeologist/eval/report.py")
    )
    assert codex.method_hash() == base
    monkeypatch.setattr(
        codex, "_runtime_files", edited("src/cobol_archaeologist/eval/detector.py")
    )
    assert codex.method_hash() != base


def test_client_warning_items_are_not_fatal():
    warning = {"type": "error", "message": "Model metadata not found"}
    stream = codex.authorize_events(
        _events(warning), tool_command=BRIDGE, aliases=[ALIAS]
    )
    assert stream.tool_logs == []


def _bash(inner: str) -> str:
    return "/bin/bash -lc " + shlex.quote(inner)


def test_malformed_bridge_call_is_rejected_not_fatal():
    item = _tool_item("read_program", {"program": "X"}, {})
    item["command"] = _bash(f"{BRIDGE} {ALIAS} read_program")
    stream = codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])
    assert stream.rejected_commands == 1 and stream.tool_logs == []


def test_bridge_call_with_shell_syntax_invalidates_the_task():
    item = _tool_item("read_program", {"program": "X"}, {})
    item["command"] = _bash(
        f"{BRIDGE} {ALIAS} read_program --arguments '{{}}' && cat /etc/passwd"
    )
    with pytest.raises(ValueError, match="shell syntax"):
        codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])


def test_equals_form_of_arguments_is_accepted():
    output = {
        "tool": "read_program",
        "sequence": 1,
        "observation_summary": "{}",
        "observation_truncated": False,
        "error": None,
    }
    item = _tool_item("read_program", {"program": "X"}, output)
    payload = json.dumps({"program": "X"})
    item["command"] = _bash(
        f"{BRIDGE} {ALIAS} read_program --arguments={shlex.quote(payload)}"
    )
    stream = codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])
    assert stream.tool_logs[0].arguments == {"program": "X"}


def test_unparseable_failed_bridge_call_is_rejected_not_fatal():
    item = _tool_item("check_finding", {}, {"infrastructure_error": "x"}, exit_code=2)
    item["command"] = (
        f'/bin/bash -lc "{BRIDGE} {ALIAS} check_finding --arguments \'{{"a": "don\'t"}}\'"'
    )
    stream = codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])
    assert stream.rejected_commands == 1


def test_unparseable_successful_command_invalidates_the_task():
    item = _tool_item("check_finding", {}, {"check": "check_finding"})
    item["command"] = (
        f'/bin/bash -lc "{BRIDGE} {ALIAS} check_finding --arguments \'{{"a": "don\'t"}}\'"'
    )
    with pytest.raises(ValueError, match="unverifiable"):
        codex.authorize_events(_events(item), tool_command=BRIDGE, aliases=[ALIAS])


def _completed(code: int, stdout: str = "", stderr: str = ""):
    import subprocess

    return subprocess.CompletedProcess([], code, stdout.encode(), stderr.encode())


def test_usage_limit_moves_the_task_to_the_next_account(monkeypatch):
    homes = []

    def fake_wsl(arguments, **_):
        if arguments[:2] == ["rm", "-rf"]:
            return _completed(0)
        home = next(a for a in arguments if a.startswith("CODEX_HOME="))
        homes.append(home)
        if home.endswith("/a"):
            return _completed(1, stderr="You've hit your usage limit. Try again later.")
        return _completed(0, stdout=_stdout())

    monkeypatch.setattr(codex, "wsl", fake_wsl)
    monkeypatch.setattr(codex, "stage_files", lambda *_: None)
    monkeypatch.setattr(codex, "_accounts", codex.Accounts(["/h/a", "/h/b"]))

    first = codex.execute_task(prompt="p", schema={}, sources={}, support_root=None)
    second = codex.execute_task(prompt="p", schema={}, sources={}, support_root=None)

    assert first.final_message == second.final_message == '{"results":[]}'
    assert homes == ["CODEX_HOME=/h/a", "CODEX_HOME=/h/b", "CODEX_HOME=/h/b"]


def test_run_stops_when_every_account_is_exhausted(monkeypatch):
    def fake_wsl(arguments, **_):
        if arguments[:2] == ["rm", "-rf"]:
            return _completed(0)
        return _completed(1, stderr="401 Unauthorized")

    monkeypatch.setattr(codex, "wsl", fake_wsl)
    monkeypatch.setattr(codex, "stage_files", lambda *_: None)
    monkeypatch.setattr(codex, "_accounts", codex.Accounts(["/h/a", "/h/b"]))

    with pytest.raises(codex.CodexAuthError, match="login expired"):
        codex.execute_task(prompt="p", schema={}, sources={}, support_root=None)


def test_other_failures_do_not_retire_the_account(monkeypatch):
    def fake_wsl(arguments, **_):
        if arguments[:2] == ["rm", "-rf"]:
            return _completed(0)
        return _completed(2, stderr="model crashed")

    accounts = codex.Accounts(["/h/a"])
    monkeypatch.setattr(codex, "wsl", fake_wsl)
    monkeypatch.setattr(codex, "stage_files", lambda *_: None)
    monkeypatch.setattr(codex, "_accounts", accounts)

    with pytest.raises(RuntimeError, match="model crashed"):
        codex.execute_task(prompt="p", schema={}, sources={}, support_root=None)
    assert accounts.current() == "/h/a"


def _stdout() -> str:
    events = [
        {"type": "thread.started", "thread_id": "t"},
        {
            "type": "item.completed",
            "item": {"id": "m", "type": "agent_message", "text": '{"results":[]}'},
        },
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    ]
    return "\n".join(json.dumps(event) for event in events)
