"""Narrow command-line bridge from a Codex task to ``RealToolLayer``.

The model receives opaque case aliases.  Alias-to-source resolution stays in a
task-local descriptor and cannot point outside that task.  Every call is
recorded before its bounded JSON observation is returned, giving the trusted
outer runner a replayable transcript for policy guards and verification.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.agent.loop import _summarize
from cobol_archaeologist.eval.codex_batch import AGENT_HUNTS
from cobol_archaeologist.model.prompt import ToolName
from cobol_archaeologist.schemas import DriftType
from cobol_archaeologist.tool_types import RunInputs, ToolLayer
from cobol_archaeologist.tools import RealToolLayer

HuntName = DriftType
DESCRIPTOR_NAME = "descriptor.json"
LOG_NAME = "tool_log.jsonl"
MAX_TOOL_CALLS_PER_HUNT = 8


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(pattern=r"^drift_9\d{5}$")
    hunt: HuntName
    tool: ToolName
    arguments: dict[str, Any]


class ToolLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    hunt: HuntName
    sequence: int = Field(ge=1)
    tool: ToolName
    arguments: dict[str, Any]
    observation_summary: str
    observation_truncated: bool
    error: str | None
    latency_ms: float = Field(ge=0)


def _source_dir(task_root: Path, alias: str) -> Path:
    descriptor_path = task_root / DESCRIPTOR_NAME
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    aliases = descriptor.get("aliases")
    if not isinstance(aliases, dict) or alias not in aliases:
        raise KeyError(f"unknown case alias {alias!r}")
    entry = aliases[alias]
    if not isinstance(entry, dict) or not isinstance(entry.get("source_dir"), str):
        raise TypeError(f"descriptor entry for {alias!r} has no source_dir")
    source = (task_root / entry["source_dir"]).resolve()
    resolved_root = task_root.resolve()
    if source != resolved_root and resolved_root not in source.parents:
        raise ValueError(f"descriptor source_dir for {alias!r} escapes task root")
    if not source.is_dir():
        raise FileNotFoundError(f"source directory for {alias!r} does not exist")
    return source


def _next_sequence(log_path: Path) -> int:
    if not log_path.exists():
        return 1
    return (
        sum(
            bool(line.strip())
            for line in log_path.read_text(encoding="utf-8").splitlines()
        )
        + 1
    )


def execute_tool_request(
    request: ToolRequest,
    *,
    task_root: Path,
    tool_factory: Callable[[Path], ToolLayer] = lambda source: RealToolLayer(
        corpus_root=source,
        copybook_paths=[source],
    ),
) -> ToolLogEntry:
    """Execute one authorized call and append its complete bounded transcript."""

    task_root = Path(task_root)
    source = _source_dir(task_root, request.alias)
    log_path = task_root / LOG_NAME
    prior_calls = (
        [
            ToolLogEntry.model_validate_json(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if log_path.exists()
        else []
    )
    if sum(
        entry.alias == request.alias and entry.hunt == request.hunt
        for entry in prior_calls
    ) >= (
        MAX_TOOL_CALLS_PER_HUNT
    ):
        raise RuntimeError(
            f"tool budget exhausted for {request.alias}/{request.hunt}: "
            f"maximum {MAX_TOOL_CALLS_PER_HUNT} calls"
        )
    tools = tool_factory(source)
    arguments = dict(request.arguments)
    if request.tool == "run_cobol" and isinstance(arguments.get("inputs"), dict):
        arguments["inputs"] = RunInputs.model_validate(arguments["inputs"])

    error: str | None = None
    observation: Any = None
    before = time.monotonic()
    try:
        observation = getattr(tools, request.tool)(**arguments)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = max(0.0, round((time.monotonic() - before) * 1000, 3))
    if error is None:
        summary, truncated = _summarize(observation)
    else:
        summary, truncated = error, False

    entry = ToolLogEntry(
        alias=request.alias,
        hunt=request.hunt,
        sequence=_next_sequence(log_path),
        tool=request.tool,
        arguments=request.arguments,
        observation_summary=summary,
        observation_truncated=truncated,
        error=error,
        latency_ms=latency_ms,
    )
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(entry.model_dump_json() + "\n")
    return entry


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alias")
    parser.add_argument("hunt", choices=AGENT_HUNTS)
    parser.add_argument("tool")
    parser.add_argument("--arguments", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        arguments = json.loads(args.arguments)
        request = ToolRequest(
            alias=args.alias,
            hunt=args.hunt,
            tool=args.tool,
            arguments=arguments,
        )
        entry = execute_tool_request(request, task_root=Path.cwd())
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "infrastructure_error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "tool": entry.tool,
                "observation_summary": entry.observation_summary,
                "observation_truncated": entry.observation_truncated,
                "error": entry.error,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
