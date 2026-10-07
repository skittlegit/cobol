"""Stdio MCP adapter over :class:`tool_types.ToolLayer`.

This module deliberately contains no parser, graph, slicing, copybook,
execution, or retrieval logic. The eleven MCP tools delegate to the frozen
ToolLayer seam and return its existing Pydantic models directly.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from cobol_archaeologist.tool_types import (
    CopybookExpansion,
    DataLayout,
    GrepResult,
    NodeRef,
    ParagraphView,
    ProgramView,
    RegSearchHit,
    RunInputs,
    RunResult,
    Slice,
    ToolLayer,
    VariableTrace,
)
from cobol_archaeologist.tools import RealToolLayer

MCP_TOOL_NAMES = (
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
)


@dataclass(frozen=True)
class ServerConfig:
    """Filesystem configuration for one local stdio server."""

    corpus_root: Path
    copybook_paths: tuple[Path, ...]


def build_server(layer: ToolLayer) -> FastMCP:
    """Register the frozen ToolLayer surface on a local MCP server."""

    if not isinstance(layer, ToolLayer):
        raise TypeError("layer must implement tool_types.ToolLayer")

    server = FastMCP(
        "COBOL Archaeologist",
        instructions=(
            "Inspect COBOL through bounded structured results and original-source "
            "pointers. Tool lookup failures are errors, not empty evidence."
        ),
        json_response=True,
    )

    @server.tool()
    def read_paragraph(program: str, name: str) -> ParagraphView:
        """Read one bounded paragraph with callers, callees, and source pointer."""

        return layer.read_paragraph(program, name)

    @server.tool()
    def read_program(program: str) -> ProgramView:
        """List a program's paragraph spans and source path."""

        return layer.read_program(program)

    @server.tool()
    def find_callers(program: str, para: str) -> list[NodeRef]:
        """Find call-graph predecessors of a program paragraph."""

        return layer.find_callers(program, para)

    @server.tool()
    def find_callees(program: str, para: str) -> list[NodeRef]:
        """Find call-graph successors of a program paragraph."""

        return layer.find_callees(program, para)

    @server.tool()
    def trace_variable(
        var: str,
        program: str | None = None,
    ) -> VariableTrace:
        """Return bounded def/use sites, optionally scoped to one program."""

        return layer.trace_variable(var, program)

    @server.tool()
    def slice_on(var: str, program: str | None = None) -> Slice:
        """Build the interprocedural statement slice for one variable."""

        return layer.slice_on(var, program)

    @server.tool()
    def resolve_copybook(name: str) -> CopybookExpansion:
        """Resolve one copybook with bounded text and an original-line map."""

        return layer.resolve_copybook(name)

    @server.tool()
    def get_data_layout(record: str) -> DataLayout:
        """Return the typed field tree and original-source pointer for a record."""

        return layer.get_data_layout(record)

    @server.tool()
    def grep(pattern: str) -> GrepResult:
        """Regex-search original program and copybook sources with a result cap."""

        return layer.grep(pattern)

    @server.tool()
    def run_cobol(
        snippet: str,
        stdin: str = "",
        files: dict[str, str] | None = None,
    ) -> RunResult:
        """Compile and execute a full program or bounded snippet via GnuCOBOL."""

        return layer.run_cobol(
            snippet,
            RunInputs(stdin=stdin, files={} if files is None else files),
        )

    @server.tool()
    def search_regulations(query: str) -> list[RegSearchHit]:
        """Search the pinned regulation index for clause-anchored hits."""

        return layer.search_regulations(query)

    return server


def parse_server_config(
    argv: Sequence[str] | None = None,
    *,
    environ: dict[str, str] | None = None,
) -> ServerConfig:
    """Parse deterministic CLI/environment configuration."""

    source = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(prog="cobol-archaeologist-mcp")
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=source.get("COBOL_CORPUS_ROOT"),
        help="directory containing COBOL program sources",
    )
    parser.add_argument(
        "--copybook-path",
        type=Path,
        action="append",
        dest="copybook_paths",
        help="COPY search directory; repeat for multiple paths",
    )
    args = parser.parse_args(argv)
    if args.corpus_root is None:
        parser.error(
            "--corpus-root or the COBOL_CORPUS_ROOT environment variable is required"
        )

    copybook_paths = args.copybook_paths
    if copybook_paths is None:
        raw_paths = source.get("COBOL_COPYBOOK_PATHS", "")
        copybook_paths = [Path(value) for value in raw_paths.split(os.pathsep) if value]
    return ServerConfig(
        corpus_root=Path(args.corpus_root),
        copybook_paths=tuple(copybook_paths),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local server over stdio; T7.2 owns network transports."""

    config = parse_server_config(argv)
    layer = RealToolLayer(
        corpus_root=config.corpus_root,
        copybook_paths=list(config.copybook_paths),
    )
    build_server(layer).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
