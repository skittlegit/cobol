"""T7.1 gates for the stdio MCP adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.mcp_server.server import (
    MCP_TOOL_NAMES,
    build_server,
    parse_server_config,
)
from cobol_archaeologist.tool_types import RunInputs

CORPUS = Path(__file__).parent / "fixtures" / "hunts" / "corpus"


def _registered_tools(server) -> dict:
    return {tool.name: tool for tool in server._tool_manager.list_tools()}


def test_mcp_registry_exactly_matches_frozen_tool_layer() -> None:
    server = build_server(StubToolLayer(CORPUS))

    assert set(_registered_tools(server)) == set(MCP_TOOL_NAMES)
    assert len(MCP_TOOL_NAMES) == 11


def test_mcp_delegates_structured_results_and_run_inputs() -> None:
    class RecordingStub(StubToolLayer):
        last_inputs: RunInputs | None = None

        def run_cobol(self, snippet: str, inputs: RunInputs | None = None):
            self.last_inputs = inputs
            return super().run_cobol(snippet, inputs)

    layer = RecordingStub(CORPUS)
    server = build_server(layer)
    tools = _registered_tools(server)

    program = asyncio.run(tools["read_program"].run({"program": "CLOSPEN1"}))
    execution = asyncio.run(
        tools["run_cobol"].run(
            {
                "snippet": "DISPLAY 'OK'",
                "stdin": "input\n",
                "files": {"control.txt": "Y\n"},
            }
        )
    )

    assert program.program == "CLOSPEN1"
    assert program.paragraphs
    assert execution.compiled_ok is True
    assert execution.stdout == "OK\n"
    assert layer.last_inputs == RunInputs(
        stdin="input\n",
        files={"control.txt": "Y\n"},
    )


def test_mcp_configuration_fails_closed_and_splits_platform_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COBOL_CORPUS_ROOT", raising=False)
    monkeypatch.delenv("COBOL_COPYBOOK_PATHS", raising=False)
    with pytest.raises(SystemExit):
        parse_server_config([])

    monkeypatch.setenv("COBOL_CORPUS_ROOT", str(CORPUS))
    monkeypatch.setenv(
        "COBOL_COPYBOOK_PATHS",
        str(CORPUS) + __import__("os").pathsep + str(CORPUS / "copybooks"),
    )
    config = parse_server_config([])

    assert config.corpus_root == CORPUS
    assert config.copybook_paths == (CORPUS, CORPUS / "copybooks")
