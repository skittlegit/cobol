"""The in-task tool bridge: tool calls and the check_finding self-check."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.eval import bridge
from cobol_archaeologist.model import verify as verify_module
from cobol_archaeologist.model.verify import LexicalEntailer
from tests.replay import ALIAS, submitted_case

FIX = Path(__file__).resolve().parent / "fixtures" / "hunts"
CORPUS = FIX / "corpus"


def _rows(case: str) -> list[dict]:
    return json.loads((FIX / "cached_decisions.json").read_text(encoding="utf-8"))[case]


@pytest.fixture()
def task(tmp_path: Path) -> Path:
    shutil.copytree(CORPUS, tmp_path / "cases" / ALIAS)
    final = _rows("d1")[-1]
    (tmp_path / bridge.DESCRIPTOR_NAME).write_text(
        json.dumps(
            {
                "aliases": {
                    ALIAS: {
                        "source_dir": f"cases/{ALIAS}",
                        "clause": final["prediction"]["regulation_clause"],
                        "program_scope": "CLOSPEN2",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _stub(source: Path) -> StubToolLayer:
    return StubToolLayer(source)


def _call_tools(task: Path, case: str) -> list[bridge.ToolLogEntry]:
    return [
        bridge.run_tool(
            ALIAS, row["tool"], row["arguments"], task_root=task, tool_factory=_stub
        )
        for row in _rows(case)
        if row["kind"] == "tool"
    ]


def test_tool_calls_are_numbered_and_logged(task):
    entries = _call_tools(task, "d1")
    assert [entry.sequence for entry in entries] == [1, 2]
    logged = (task / bridge.LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert len(logged) == 2


def test_unknown_tool_and_unknown_alias_are_refused(task):
    with pytest.raises(ValueError, match="unknown tool"):
        bridge.run_tool(ALIAS, "rm", {}, task_root=task, tool_factory=_stub)
    with pytest.raises(KeyError):
        bridge.run_tool(
            "drift_999999", "grep", {"pattern": "X"}, task_root=task, tool_factory=_stub
        )


def test_tool_budget_is_enforced(task, monkeypatch):
    monkeypatch.setattr(bridge, "MAX_TOOL_CALLS", 1)
    bridge.run_tool(ALIAS, "grep", {"pattern": "PEN"}, task_root=task, tool_factory=_stub)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        bridge.run_tool(
            ALIAS, "grep", {"pattern": "PEN"}, task_root=task, tool_factory=_stub
        )


def _draft(task: Path, mutate=None) -> dict:
    logs = bridge._logs(task)
    case = submitted_case(_rows("d1")[-1], logs).model_dump(mode="json")
    case.pop("alias")
    if mutate:
        mutate(case)
    return case


def test_check_finding_accepts_a_valid_draft(task, monkeypatch):
    monkeypatch.setattr(verify_module, "default_entailer", LexicalEntailer)
    _call_tools(task, "d1")
    result = bridge.check_finding(ALIAS, _draft(task), task_root=task, tool_factory=_stub)
    assert result["accepted"] is True
    assert result["rejection"] is None
    assert result["checks_remaining"] == bridge.MAX_CHECKS - 1


def test_check_finding_reports_the_exact_rejection(task, monkeypatch):
    monkeypatch.setattr(verify_module, "default_entailer", LexicalEntailer)
    _call_tools(task, "d1")

    def cite_missing_step(case):
        case["evidence_ledger"][0]["observation_step"] = 42

    result = bridge.check_finding(
        ALIAS, _draft(task, cite_missing_step), task_root=task, tool_factory=_stub
    )
    assert result["accepted"] is False
    assert "ledger step 42" in result["rejection"]


def test_check_budget_is_enforced(task, monkeypatch):
    monkeypatch.setattr(verify_module, "default_entailer", LexicalEntailer)
    monkeypatch.setattr(bridge, "MAX_CHECKS", 1)
    _call_tools(task, "d1")
    bridge.check_finding(ALIAS, _draft(task), task_root=task, tool_factory=_stub)
    with pytest.raises(RuntimeError, match="check budget exhausted"):
        bridge.check_finding(ALIAS, _draft(task), task_root=task, tool_factory=_stub)
