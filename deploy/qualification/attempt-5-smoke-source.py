"""Actual stdio MCP smoke, executed by the clean bundle interpreter."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TOOLS = {
    "read_paragraph",
    "read_program",
    "find_callers",
    "find_callees",
    "trace_variable",
    "slice_on",
    "resolve_copybook",
    "get_data_layout",
    "grep",
    "run_cobol",
    "search_regulations",
}


async def smoke(bundle, corpus):
    assert sys.version_info[:2] == (3, 12) and sys.prefix != sys.base_prefix
    distribution = importlib.metadata.distribution("cobol-archaeologist")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    assert not direct.get("dir_info", {}).get("editable", False)
    scratch = Path(sys.prefix) / "offline-smoke-temp"
    scratch.mkdir(exist_ok=False)
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            str(bundle / "offline.py"),
            "serve",
            "--bundle",
            str(bundle),
            "--corpus",
            str(corpus),
        ],
        cwd=str(bundle),
        env={
            **os.environ,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PIP_NO_INDEX": "1",
            "TEMP": str(scratch),
            "TMP": str(scratch),
        },
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listed = await session.list_tools()
        assert {tool.name for tool in listed.tools} == TOOLS
        results = {}
        for name, args in (
            ("read_program", {"program": "CLOSPEN1"}),
            ("slice_on", {"var": "WS-WORKING-DAYS", "program": "CLOSPEN1"}),
            ("search_regulations", {"query": "credit card closure seven working days"}),
            (
                "run_cobol",
                {
                    "snippet": "IDENTIFICATION DIVISION.\nPROGRAM-ID. CICSCASE.\nPROCEDURE DIVISION.\nEXEC CICS RETURN END-EXEC.\nSTOP RUN."
                },
            ),
        ):
            result = await session.call_tool(name, args)
            results[name] = result.model_dump(mode="json")
            if name != "run_cobol":
                assert not result.isError, results[name]
        assert results["search_regulations"]["content"], (
            "No clause-anchored search result"
        )
        execution = results["run_cobol"]
        # A missing compiler is explicitly unavailable; a supported compiler
        # returns compiled_ok=false for unsupported CICS. Neither is a pass.
        assert (
            execution["isError"]
            or execution.get("structuredContent", {}).get("compiled_ok") is False
        )
        return {
            "status": "PASS",
            "transport": "stdio",
            "tool_count": len(listed.tools),
            "network_policy": "Python socket audit guard plus hub offline; no OS namespace claim",
            "tier1": "unavailable_for_CICS",
            "installed_distribution": str(distribution.locate_file("")),
            "editable": False,
            "results": results,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(smoke(args.bundle.resolve(), args.corpus.resolve())),
            sort_keys=True,
        )
    )
