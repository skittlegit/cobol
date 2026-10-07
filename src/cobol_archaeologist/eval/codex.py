"""Run one isolated Codex task inside WSL and return host-trusted results.

Every provider call in this repository goes through :func:`execute_task`.
Codex authenticates with the user's ChatGPT login (API keys are never
forwarded).  A task directory contains only opaque case aliases, the
detector-visible prompt/context, and materialized source.  The only command
the model may run is the tool bridge (:mod:`cobol_archaeologist.eval.bridge`);
the host reconstructs tool observations from the Codex event stream, never
from files the model could edit.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
import threading
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.eval.bridge import (
    BRIDGE_MODULE,
    CHECK_OPERATION,
    ToolLogEntry,
)
from cobol_archaeologist.eval.materialize import MaterializedSource

ROOT = Path(__file__).resolve().parents[3]

# One place for provider identity and WSL locations.
MODEL_ID = os.environ.get("COBOL_ARCH_MODEL", "gpt-6-luna")
REASONING_EFFORT = os.environ.get("COBOL_ARCH_EFFORT", "max")
WSL_DISTRO = os.environ.get("COBOL_ARCH_WSL_DISTRO", "Ubuntu")
WSL_HOME = os.environ.get("COBOL_ARCH_WSL_HOME", "/home/deepa")
CODEX_BINARY = os.environ.get("COBOL_ARCH_CODEX", f"{WSL_HOME}/.local/bin/codex")
UV_BINARY = f"{WSL_HOME}/.local/bin/uv"
SUPPORT_BASE = f"{WSL_HOME}/.cache/cobol-archaeologist/support"
TASK_BASE = f"{WSL_HOME}/.cache/cobol-archaeologist/tasks"
# ChatGPT accounts, one Codex home each (each holds its own auth.json). Tasks
# use the first home that is logged in; when its usage limit is hit, the task
# is retried on the next one. Log a second account in with
# `CODEX_HOME=~/.codex-b codex login --device-auth` inside WSL.
CODEX_HOMES = tuple(
    os.environ.get(
        "COBOL_ARCH_CODEX_HOMES", f"{WSL_HOME}/.codex:{WSL_HOME}/.codex-b"
    ).split(":")
)

_ENV_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "CODEX_HOME",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
)
# "error" items are client warnings (for example missing model metadata); a
# real failure ends the process with a non-zero exit code instead.
_PASSIVE_ITEM_TYPES = frozenset({"agent_message", "reasoning", "error"})
_AUTH_FAILURES = (
    "401 Unauthorized",
    "access token could not be refreshed",
    "Please log out and sign in again",
)


_LIMIT_FAILURES = (
    "usage limit",
    "usage_limit",
    "429 Too Many Requests",
    "rate limit reached",
)


class CodexAuthError(RuntimeError):
    """No Codex account can run tasks (login expired or limits reached)."""


class _AccountUnusable(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Accounts:
    """Rotate tasks across the logged-in Codex homes."""

    def __init__(self, homes: Sequence[str]):
        self._homes = list(homes)
        self._dead: dict[str, str] = {}
        self._lock = threading.Lock()

    def current(self) -> str:
        with self._lock:
            for home in self._homes:
                if home not in self._dead:
                    return home
        raise CodexAuthError(
            "no usable Codex account: "
            + "; ".join(f"{home}: {why}" for home, why in self._dead.items())
            + f". Log in again (`wsl -d {WSL_DISTRO} -- env CODEX_HOME=<home> "
            f"{CODEX_BINARY} login --device-auth`) or wait for the limit to reset"
        )

    def retire(self, home: str, reason: str) -> None:
        with self._lock:
            self._dead.setdefault(home, reason)


def _logged_in_homes() -> list[str]:
    return [
        home
        for home in CODEX_HOMES
        if wsl(["test", "-s", f"{home}/auth.json"]).returncode == 0
    ]


_accounts: Accounts | None = None


def accounts() -> Accounts:
    global _accounts
    if _accounts is None:
        _accounts = Accounts(_logged_in_homes())
    return _accounts


_PASSIVE_EVENT_TYPES = frozenset({"thread.started", "turn.started", "turn.completed"})


# --------------------------------------------------------------------------
# WSL plumbing
# --------------------------------------------------------------------------


def sanitized_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if source is None else source
    return {k: v for k, v in source.items() if k.upper() in _ENV_ALLOWLIST}


def wsl(
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    timeout: float = 120,
) -> subprocess.CompletedProcess[bytes]:
    command = (
        list(arguments)
        if sys.platform == "linux"
        else ["wsl", "-d", WSL_DISTRO, "--", *arguments]
    )
    return subprocess.run(
        command,
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=sanitized_environment(),
    )


def require_ok(result: subprocess.CompletedProcess[bytes], action: str) -> None:
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"{action} failed ({result.returncode}): {stderr[-4000:]}")


def _tar_bytes(files: Mapping[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, content in sorted(files.items()):
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"unsafe task archive path {name!r}")
            info = tarfile.TarInfo(pure.as_posix())
            info.size = len(content)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(content))
    return stream.getvalue()


def stage_files(root: str, files: Mapping[str, bytes]) -> None:
    require_ok(wsl(["mkdir", "-p", root]), f"create {root}")
    require_ok(
        wsl(["tar", "-xf", "-", "-C", root], input_bytes=_tar_bytes(files)),
        f"stage {root}",
    )


# --------------------------------------------------------------------------
# Support runtime: the package installed in WSL so the bridge can run tools
# --------------------------------------------------------------------------


def _runtime_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {"pyproject.toml": (ROOT / "pyproject.toml").read_bytes()}
    for path in sorted((ROOT / "src").rglob("*.py")):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in sorted((ROOT / "vendor" / "tree-sitter-cobol").rglob("*")):
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    cache = ROOT / "tests" / "fixtures" / "verify" / "nli_cache.jsonl"
    if cache.exists():
        files[cache.relative_to(ROOT).as_posix()] = cache.read_bytes()
    return files


# Code that does not change what a detector or baseline answers. Editing it
# must not invalidate stored results.
_NOT_METHOD = (
    "pyproject.toml",
    "src/cobol_archaeologist/benchmark/",
    "src/cobol_archaeologist/migration/",
    "src/cobol_archaeologist/mcp_server/",
    "src/cobol_archaeologist/cli.py",
    "src/cobol_archaeologist/eval/report.py",
    "src/cobol_archaeologist/eval/metrics.py",
    "src/cobol_archaeologist/eval/statistics.py",
    "src/cobol_archaeologist/eval/calibration.py",
    "src/cobol_archaeologist/eval/trajectory.py",
)


def _digest(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, payload in sorted(files.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def runtime_identity() -> str:
    """SHA-256 over every file the support runtime installs."""

    return _digest(_runtime_files())


def method_hash() -> str:
    """SHA-256 over the code that determines detector and baseline answers.

    Stored results carry it in their run key, so any change to prompts, tools,
    guards, or the verifier replaces old results on the next run.
    """

    return _digest(
        {
            name: payload
            for name, payload in _runtime_files().items()
            if not name.startswith(_NOT_METHOD)
        }
    )


def prepare_support_runtime() -> tuple[str, str]:
    """Install the current source into a WSL venv keyed by its content hash.

    Returns ``(support_root, identity)``.  Older runtimes are replaced: only
    the runtime matching the current source is kept.
    """

    identity = runtime_identity()
    support_root = f"{SUPPORT_BASE}/{identity[:16]}"
    marker = f"{support_root}/.ready"
    if wsl(["test", "-f", marker]).returncode == 0:
        return support_root, identity
    require_ok(wsl(["rm", "-rf", "--", SUPPORT_BASE]), "remove stale support runtimes")
    stage_files(support_root, _runtime_files())
    python = f"{support_root}/.venv/bin/python"
    steps = [
        (
            [UV_BINARY, "venv", "--python", "3.12", "--seed", f"{support_root}/.venv"],
            "create WSL venv",
        ),
        (
            [
                UV_BINARY,
                "pip",
                "install",
                "--python",
                python,
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
                "torch",
            ],
            "install CPU torch",
        ),
        (
            [
                UV_BINARY,
                "pip",
                "install",
                "--python",
                python,
                "-e",
                support_root,
                "setuptools>=68",
                "transformers",
            ],
            "install support package",
        ),
        (
            [
                python,
                "-c",
                (
                    "from cobol_archaeologist.parser._grammar import get_language; "
                    "get_language()"
                ),
            ],
            "build COBOL grammar",
        ),
    ]
    for arguments, action in steps:
        require_ok(wsl(arguments, timeout=1800), action)
    require_ok(wsl(["touch", marker]), "mark support runtime ready")
    return support_root, identity


def bridge_command(support_root: str) -> str:
    return f"{support_root}/.venv/bin/python -m {BRIDGE_MODULE}"


def check_login() -> str:
    statuses = []
    for home in _logged_in_homes():
        result = wsl(["env", f"CODEX_HOME={home}", CODEX_BINARY, "login", "status"])
        status = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        if result.returncode == 0 and "ChatGPT" in status:
            statuses.append(f"{home}: {status.strip()}")
    if not statuses:
        raise RuntimeError("Codex must be logged in through ChatGPT")
    return "\n".join(statuses)


def codex_version() -> str:
    result = wsl([CODEX_BINARY, "--version"])
    require_ok(result, "read Codex version")
    return result.stdout.decode("utf-8", errors="replace").strip()


# --------------------------------------------------------------------------
# Structured output and event parsing
# --------------------------------------------------------------------------


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic schema to the Codex structured-output subset."""

    schema = model.model_json_schema()

    def normalize(node: Any) -> None:
        if isinstance(node, dict):
            for keyword in (
                "default",
                "format",
                "maxItems",
                "maxLength",
                "maximum",
                "minItems",
                "minLength",
                "minimum",
                "multipleOf",
                "pattern",
                "uniqueItems",
            ):
                node.pop(keyword, None)
            prefix_items = node.pop("prefixItems", None)
            if isinstance(prefix_items, list) and prefix_items:
                node["items"] = (
                    prefix_items[0]
                    if all(item == prefix_items[0] for item in prefix_items)
                    else {"anyOf": prefix_items}
                )
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


class CodexUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ParsedEvents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_message: str
    usage: CodexUsage
    events: list[dict[str, Any]]


def parse_events(stdout: str) -> ParsedEvents:
    """Parse ``codex exec --json`` output."""

    events: list[dict[str, Any]] = []
    final_message: str | None = None
    usage = CodexUsage()
    for number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Codex event line {number} is not JSON") from exc
        if not isinstance(event, dict):
            raise TypeError(f"Codex event line {number} is not an object")
        events.append(event)
        if event.get("type") == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str):
                    final_message = text
        if event.get("type") == "turn.completed" and isinstance(
            event.get("usage"), dict
        ):
            usage = CodexUsage.model_validate(event["usage"])
    if final_message is None:
        raise ValueError("Codex event stream has no completed agent message")
    return ParsedEvents(final_message=final_message, usage=usage, events=events)


def _split_command(command: str) -> list[str]:
    """Split a Codex command event, unwrapping ``bash -lc "<script>"``."""

    tokens = shlex.split(command, posix=True)
    if len(tokens) == 3 and tokens[0].endswith("bash") and tokens[1] in {"-lc", "-c"}:
        return shlex.split(tokens[2], posix=True)
    return tokens


_SHELL_OPERATORS = ("&&", "||", "|", ";", ">", ">>", "<", "&", "<<")


class _MalformedBridgeCall(ValueError):
    """A plain bridge call with the wrong arguments; the bridge rejects it."""


class _UnparseableCommand(ValueError):
    """A command whose shell quoting cannot be parsed."""


def _parse_bridge_call(
    command: str,
    *,
    prefix: list[str],
    aliases: frozenset[str],
) -> tuple[str, str, dict[str, Any]]:
    try:
        tokens = _split_command(command)
    except ValueError as exc:
        raise _UnparseableCommand(f"unparseable command: {command[:300]!r}") from exc
    if tokens[: len(prefix)] != prefix:
        raise ValueError(f"command is not the tool bridge: {command[:300]!r}")
    suffix = tokens[len(prefix) :]
    if any(t in _SHELL_OPERATORS or "$(" in t or "`" in t for t in suffix):
        raise ValueError(f"bridge call combined with shell syntax: {command[:300]!r}")
    if len(suffix) == 3 and suffix[2].startswith("--arguments="):
        suffix = [suffix[0], suffix[1], "--arguments", suffix[2][len("--arguments=") :]]
    if len(suffix) != 4 or suffix[2] != "--arguments":
        raise _MalformedBridgeCall(command[:300])
    alias, operation, _, raw = suffix
    if alias not in aliases:
        raise ValueError(f"bridge invocation uses unknown alias {alias!r}")
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _MalformedBridgeCall(command[:300]) from exc
    if not isinstance(arguments, dict):
        raise _MalformedBridgeCall(command[:300])
    return alias, operation, arguments


def _bridge_payload(text: str) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("bridge output must be exactly one JSON line")
    payload = json.loads(lines[0])
    if not isinstance(payload, dict):
        raise TypeError("bridge output is not an object")
    return payload


@dataclass
class AuthorizedStream:
    tool_logs: list[ToolLogEntry] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    rejected_commands: int = 0


def authorize_events(
    parsed: ParsedEvents,
    *,
    tool_command: str | None,
    aliases: Iterable[str] = (),
) -> AuthorizedStream:
    """Reconstruct trusted tool logs from completed bridge commands.

    Any non-bridge command, file change, web search, or MCP call makes the
    whole task invalid.  Bridge invocations that the bridge itself rejected
    (bad arguments, exhausted budget) are counted but carry no observation.
    """

    alias_set = frozenset(aliases)
    prefix = shlex.split(tool_command, posix=True) if tool_command else []
    started: dict[str, str] = {}
    stream = AuthorizedStream()
    for event in parsed.events:
        event_type = event.get("type")
        if event_type in _PASSIVE_EVENT_TYPES:
            continue
        if event_type not in {"item.started", "item.completed"}:
            raise ValueError(f"unauthorized Codex event type {event_type!r}")
        item = event.get("item")
        if not isinstance(item, dict):
            raise TypeError("Codex item event has no object item")
        if item.get("type") in _PASSIVE_ITEM_TYPES:
            continue
        if item.get("type") != "command_execution":
            raise ValueError(f"unauthorized Codex item type {item.get('type')!r}")
        if tool_command is None:
            raise ValueError("this task does not authorize command execution")
        item_id, command = item.get("id"), item.get("command")
        if not isinstance(item_id, str) or not isinstance(command, str):
            raise TypeError("Codex command event lacks id/command")
        try:
            alias, operation, arguments = _parse_bridge_call(
                command, prefix=prefix, aliases=alias_set
            )
        except _MalformedBridgeCall:
            # The bridge itself rejects such calls; they carry no observation.
            if event_type == "item.completed":
                stream.rejected_commands += 1
            continue
        except _UnparseableCommand:
            # Broken shell quoting: bash fails before anything runs. Only a
            # failed attempt is safe to ignore; a "successful" one is not
            # verifiable and invalidates the task.
            if event_type == "item.started":
                continue
            if item.get("exit_code") == 0 or BRIDGE_MODULE not in command:
                raise ValueError(f"unverifiable command: {command[:300]!r}") from None
            stream.rejected_commands += 1
            continue
        if event_type == "item.started":
            started[item_id] = command
            continue
        if started.pop(item_id, None) != command:
            raise ValueError("completed command has no matching start event")
        try:
            payload = _bridge_payload(str(item.get("aggregated_output", "")))
        except (ValueError, TypeError):
            stream.rejected_commands += 1
            continue
        if item.get("exit_code") != 0 or "infrastructure_error" in payload:
            stream.rejected_commands += 1
            continue
        if operation == CHECK_OPERATION:
            stream.checks.append({"alias": alias, **payload})
            continue
        summary = payload.get("observation_summary")
        if payload.get("tool") != operation or not isinstance(summary, str):
            raise ValueError("bridge output does not match its invocation")
        stream.tool_logs.append(
            ToolLogEntry(
                alias=alias,
                sequence=payload["sequence"],
                tool=operation,
                arguments=arguments,
                observation_summary=summary,
                observation_truncated=payload["observation_truncated"],
                error=payload["error"],
                latency_ms=0.0,
            )
        )
    if started:
        raise ValueError("Codex event stream ended with incomplete commands")
    return stream


# --------------------------------------------------------------------------
# Task execution
# --------------------------------------------------------------------------


class TaskResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    final_message: str
    usage: CodexUsage
    tool_logs: list[ToolLogEntry]
    checks: list[dict[str, Any]]
    rejected_commands: int
    events_sha256: str


def exec_arguments(
    task_root: str, *, allow_bridge: bool, codex_home: str = CODEX_HOMES[0]
) -> list[str]:
    return [
        "env",
        "-i",
        f"HOME={WSL_HOME}",
        f"CODEX_HOME={codex_home}",
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG=C.UTF-8",
        "TERM=dumb",
        "HF_HUB_OFFLINE=1",
        "TRANSFORMERS_OFFLINE=1",
        CODEX_BINARY,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write" if allow_bridge else "read-only",
        "-m",
        MODEL_ID,
        "-c",
        f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--output-schema",
        f"{task_root}/output_schema.json",
        "-o",
        f"{task_root}/final.json",
        "-C",
        task_root,
        "-",
    ]


def _run_codex(
    task_root: str, prompt: str, allow_bridge: bool, home: str, timeout_s: float
) -> str:
    result = wsl(
        exec_arguments(task_root, allow_bridge=allow_bridge, codex_home=home),
        input_bytes=prompt.encode(),
        timeout=timeout_s,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace")
        text = stderr + stdout
        if any(marker in text for marker in _AUTH_FAILURES):
            raise _AccountUnusable("login expired")
        if any(marker.lower() in text.lower() for marker in _LIMIT_FAILURES):
            raise _AccountUnusable("usage limit reached")
        raise RuntimeError(f"Codex task failed ({result.returncode}): {text[-4000:]}")
    return stdout


def execute_task(
    *,
    prompt: str,
    schema: dict[str, Any],
    sources: Mapping[str, MaterializedSource],
    support_root: str | None,
    descriptor: Mapping[str, Any] | None = None,
    timeout_s: float = 1800,
) -> TaskResult:
    """Stage, run, authorize, and clean up one Codex task."""

    task_root = f"{TASK_BASE}/{uuid.uuid4().hex}"
    case_descriptor: dict[str, Any] = {"aliases": {}}
    files: dict[str, bytes] = {
        "prompt.txt": prompt.encode(),
        "output_schema.json": json.dumps(schema, sort_keys=True).encode(),
    }
    for alias, source in sources.items():
        entry = dict((descriptor or {}).get(alias, {}))
        entry["source_dir"] = f"cases/{alias}"
        case_descriptor["aliases"][alias] = entry
        for filename, text in source.files.items():
            pure = PurePosixPath(filename)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"unsafe materialized filename {filename!r}")
            files[f"cases/{alias}/{pure.as_posix()}"] = text.encode()
    files["descriptor.json"] = json.dumps(case_descriptor, sort_keys=True).encode()
    stage_files(task_root, files)
    try:
        while True:
            home = accounts().current()
            try:
                stdout = _run_codex(task_root, prompt, bool(sources), home, timeout_s)
                break
            except _AccountUnusable as exc:
                accounts().retire(home, exc.reason)
        parsed = parse_events(stdout)
        stream = authorize_events(
            parsed,
            tool_command=bridge_command(support_root) if sources else None,
            aliases=sources,
        )
    finally:
        wsl(["rm", "-rf", "--", task_root])
    events_sha256 = hashlib.sha256(
        json.dumps(parsed.events, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return TaskResult(
        final_message=parsed.final_message,
        usage=parsed.usage,
        tool_logs=stream.tool_logs,
        checks=stream.checks,
        rejected_commands=stream.rejected_commands,
        events_sha256=events_sha256,
    )
