"""Call the actual Linux container MCP tools over stdio with network disabled."""

from __future__ import annotations

import argparse
import asyncio
import json
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


async def smoke(image, corpus):
    mount = str(corpus.resolve())
    parameters = StdioServerParameters(
        command="docker",
        args=[
            "run",
            "--rm",
            "--interactive",
            "--network=none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,exec,mode=1777",
            "--user",
            "65532:65532",
            "--mount",
            f"type=bind,source={mount},target=/corpus,readonly",
            "--mount",
            f"type=bind,source={mount},target=/copybooks,readonly",
            image,
        ],
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        assert {t.name for t in tools.tools} == TOOLS
        results = {}
        for name, arguments in (
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
            result = await session.call_tool(name, arguments)
            assert not result.isError, result.model_dump(mode="json")
            results[name] = result.model_dump(mode="json")
        assert results["read_program"]["structuredContent"]["paragraphs"]
        assert results["slice_on"]["structuredContent"]["statements"]
        assert results["search_regulations"]["content"]
        assert results["run_cobol"]["structuredContent"]["compiled_ok"] is False
        batch = await session.call_tool(
            "run_cobol", {"snippet": "DISPLAY 'OFFLINE-OK'"}
        )
        assert not batch.isError, batch.model_dump(mode="json")
        assert batch.structuredContent["compiled_ok"] is True
        assert "OFFLINE-OK" in batch.structuredContent["stdout"]
        results["run_cobol_batch"] = batch.model_dump(mode="json")
        return {
            "schema_version": "offline-linux-container-stdio-smoke-v1",
            "status": "PASS",
            "transport": "stdio",
            "image": image,
            "tool_count": len(tools.tools),
            "network": "none",
            "uid": 65532,
            "gid": 65532,
            "rootfs": "read_only",
            "corpus_mount": "read_only",
            "model_payload": "verified_local_snapshots",
            "retrieval": "hybrid_rerank",
            "tier1": "unavailable_for_CICS",
            "results": results,
        }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True)
    p.add_argument("--corpus", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(asyncio.run(smoke(a.image, a.corpus)), sort_keys=True))
