"""T7.1 gates for the stdio MCP adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.mcp_server.server import (
    MCP_TOOL_NAMES,
    build_server,
    parse_server_config,
)
from cobol_archaeologist.tool_types import RunInputs

CORPUS = Path(__file__).parent / "fixtures" / "hunts" / "corpus"


def test_mcp_registry_exactly_matches_frozen_tool_layer() -> None:
    server = build_server(StubToolLayer(CORPUS))

    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == set(MCP_TOOL_NAMES)
    assert len(MCP_TOOL_NAMES) == 11


def test_mcp_tool_failures_reach_the_client_with_their_reason() -> None:
    class FailingStub(StubToolLayer):
        def read_program(self, program: str):
            raise KeyError(f"unknown program {program}")

    server = build_server(FailingStub(CORPUS))

    with pytest.raises(ToolError, match="unknown program NOPE"):
        asyncio.run(server.call_tool("read_program", {"program": "NOPE"}))


def test_mcp_delegates_structured_results_and_run_inputs() -> None:
    class RecordingStub(StubToolLayer):
        last_inputs: RunInputs | None = None

        def run_cobol(self, snippet: str, inputs: RunInputs | None = None):
            self.last_inputs = inputs
            return super().run_cobol(snippet, inputs)

    layer = RecordingStub(CORPUS)
    server = build_server(layer)

    program = asyncio.run(
        server.call_tool("read_program", {"program": "CLOSPEN1"})
    ).structured_content
    execution = asyncio.run(
        server.call_tool(
            "run_cobol",
            {
                "snippet": "DISPLAY 'OK'",
                "stdin": "input\n",
                "files": {"control.txt": "Y\n"},
            },
        )
    ).structured_content

    assert program["program"] == "CLOSPEN1"
    assert program["paragraphs"]
    assert execution["compiled_ok"] is True
    assert execution["stdout"] == "OK\n"
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
