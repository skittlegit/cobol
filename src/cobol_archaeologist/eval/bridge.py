"""Command-line bridge a Codex task uses to call the analysis tools.

Usage inside a task directory::

    python -m cobol_archaeologist.eval.bridge ALIAS OPERATION --arguments 'JSON'

``OPERATION`` is either a ``ToolLayer`` method (``read_program``, ``grep``,
``slice_on`` ...) or ``check_finding``.  Tool calls are numbered per alias; a
finding's evidence ledger cites those sequence numbers.  ``check_finding``
runs the exact host-side checks (ledger, policy guard, verifier) on a draft
final answer and reports any rejection, so the model can correct it before
submitting.  It sees only detector-visible inputs.  The host re-runs every
check on the final answer from trusted logs, so ``check_finding`` can never
weaken a rule.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.model.prompt import ToolName
from cobol_archaeologist.tool_types import RunInputs, ToolLayer

BRIDGE_MODULE = "cobol_archaeologist.eval.bridge"
CHECK_OPERATION = "check_finding"
DESCRIPTOR_NAME = "descriptor.json"
LOG_NAME = "tool_log.jsonl"
MAX_TOOL_CALLS = 24
MAX_CHECKS = 6
OBSERVATION_CAP_CHARS = 4000


class ToolLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    sequence: int = Field(ge=1)
    tool: ToolName
    arguments: dict[str, Any]
    observation_summary: str
    observation_truncated: bool
    error: str | None
    latency_ms: float = Field(ge=0)


def summarize(observation: Any) -> tuple[str, bool]:
    """Bound an observation while preserving its typed source pointers."""

    if isinstance(observation, BaseModel):
        value = observation.model_dump(mode="json")
        truncated = bool(getattr(observation, "truncated", False))
    elif isinstance(observation, list):
        value = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in observation
        ]
        truncated = any(bool(getattr(item, "truncated", False)) for item in observation)
    else:
        value = observation
        truncated = False
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) > OBSERVATION_CAP_CHARS:
        return rendered[: OBSERVATION_CAP_CHARS - 1] + "…", True
    return rendered, truncated


def _descriptor_entry(task_root: Path, alias: str) -> dict[str, Any]:
    descriptor = json.loads((task_root / DESCRIPTOR_NAME).read_text(encoding="utf-8"))
    aliases = descriptor.get("aliases", {})
    if alias not in aliases:
        raise KeyError(f"unknown case alias {alias!r}")
    return aliases[alias]


def _source_dir(task_root: Path, alias: str) -> Path:
    entry = _descriptor_entry(task_root, alias)
    source = (task_root / entry["source_dir"]).resolve()
    root = task_root.resolve()
    if root not in source.parents:
        raise ValueError(f"source_dir for {alias!r} escapes the task root")
    if not source.is_dir():
        raise FileNotFoundError(f"source directory for {alias!r} does not exist")
    return source


def _logs(task_root: Path) -> list[ToolLogEntry]:
    path = task_root / LOG_NAME
    if not path.exists():
        return []
    return [
        ToolLogEntry.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _default_tools(source: Path) -> ToolLayer:
    from cobol_archaeologist.tools import RealToolLayer

    return RealToolLayer(corpus_root=source, copybook_paths=[source])


def run_tool(
    alias: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    task_root: Path,
    tool_factory: Callable[[Path], ToolLayer] = _default_tools,
) -> ToolLogEntry:
    """Execute one tool call and append it to the task log."""

    if tool not in ToolName.__args__:  # type: ignore[attr-defined]
        raise ValueError(f"unknown tool {tool!r}")
    source = _source_dir(task_root, alias)
    prior = [entry for entry in _logs(task_root) if entry.alias == alias]
    if len(prior) >= MAX_TOOL_CALLS:
        raise RuntimeError(f"tool budget exhausted: maximum {MAX_TOOL_CALLS} calls")
    tools = tool_factory(source)
    call_arguments = dict(arguments)
    if tool == "run_cobol" and isinstance(call_arguments.get("inputs"), dict):
        call_arguments["inputs"] = RunInputs.model_validate(call_arguments["inputs"])
    error: str | None = None
    observation: Any = None
    started = time.monotonic()
    try:
        observation = getattr(tools, tool)(**call_arguments)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = max(0.0, round((time.monotonic() - started) * 1000, 3))
    summary, truncated = (error, False) if error else summarize(observation)
    entry = ToolLogEntry(
        alias=alias,
        sequence=len(prior) + 1,
        tool=tool,
        arguments=arguments,
        observation_summary=summary,
        observation_truncated=truncated,
        error=error,
        latency_ms=latency_ms,
    )
    with (task_root / LOG_NAME).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(entry.model_dump_json() + "\n")
    return entry


def check_finding(
    alias: str,
    draft: dict[str, Any],
    *,
    task_root: Path,
    tool_factory: Callable[[Path], ToolLayer] = _default_tools,
) -> dict[str, Any]:
    """Run the host's final-answer checks on a draft and report the outcome."""

    from cobol_archaeologist.eval.detector import (
        SubmittedCase,
        finalize_case,
    )
    from cobol_archaeologist.model.verify import default_entailer
    from cobol_archaeologist.schemas import RegulationClause

    checks_path = task_root / "checks.count"
    used = int(checks_path.read_text()) if checks_path.exists() else 0
    if used >= MAX_CHECKS:
        raise RuntimeError(f"check budget exhausted: maximum {MAX_CHECKS} checks")
    checks_path.write_text(str(used + 1))
    entry = _descriptor_entry(task_root, alias)
    submitted = SubmittedCase.model_validate({**draft, "alias": alias})
    outcome = finalize_case(
        submitted,
        clause=RegulationClause.model_validate(entry["clause"]),
        program_scope=entry["program_scope"],
        instance_id="drift_000000",
        logs=[log for log in _logs(task_root) if log.alias == alias],
        tools=tool_factory(_source_dir(task_root, alias)),
        entailer=default_entailer(),
        token_count=0,
        token_count_recorded=False,
    )
    return {
        "check": CHECK_OPERATION,
        "accepted": not outcome.abstained or submitted.response.kind == "abstain",
        "outcome": "abstain" if outcome.abstained else "finding",
        "rejection": outcome.abstention_reason
        if outcome.abstained and submitted.response.kind == "finding"
        else None,
        "verification_tier": (
            int(outcome.verification_tier)
            if outcome.verification_tier is not None
            else None
        ),
        "checks_remaining": MAX_CHECKS - used - 1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alias")
    parser.add_argument("operation")
    parser.add_argument("--arguments", required=True)
    args = parser.parse_args(argv)
    task_root = Path.cwd()
    try:
        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise TypeError("--arguments must be one JSON object")
        if args.operation == CHECK_OPERATION:
            payload = check_finding(args.alias, arguments, task_root=task_root)
        else:
            entry = run_tool(args.alias, args.operation, arguments, task_root=task_root)
            payload = {
                "tool": entry.tool,
                "sequence": entry.sequence,
                "observation_summary": entry.observation_summary,
                "observation_truncated": entry.observation_truncated,
                "error": entry.error,
            }
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"infrastructure_error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
