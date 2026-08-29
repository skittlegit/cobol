"""Native-Windows fallback for isolated ChatGPT-authenticated Codex tasks."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath

from cobol_archaeologist.eval.codex_batch import (
    authorize_codex_event_stream,
    parse_codex_events,
    sanitized_codex_environment,
)
from cobol_archaeologist.eval.codex_live import (
    CodexTaskExecution,
    _canonical_hash,
    codex_request_sha256,
)
from cobol_archaeologist.eval.materialize import MaterializedSource

DEFAULT_NATIVE_TASK_BASE = (
    Path(__file__).resolve().parents[3] / ".tmp" / "codex-config3-tasks"
)


def native_codex_exec_arguments(
    *,
    codex_binary: str,
    task_root: Path,
    model_id: str,
    reasoning_effort: str,
    allow_tool_bridge: bool = True,
) -> list[str]:
    """Return the native equivalent of the frozen ephemeral WSL invocation."""

    return [
        codex_binary,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write" if allow_tool_bridge else "read-only",
        "-m",
        model_id,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema",
        str(task_root / "output_schema.json"),
        "-o",
        str(task_root / "final.json"),
        "-C",
        str(task_root),
        "-",
    ]


def native_tool_command(
    python_executable: str | None = None,
    *,
    repository_root: Path | None = None,
) -> str:
    root = Path(repository_root or Path(__file__).resolve().parents[3]).resolve()
    if python_executable:
        python = Path(python_executable)
    else:
        candidates = (
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
            Path(sys.executable),
        )
        python = next((candidate for candidate in candidates if candidate.is_file()), candidates[-1])
    if not python.is_file():
        raise RuntimeError(f"frozen native Python does not exist: {python}")
    return subprocess.list2cmdline(
        [
            str(python.resolve()),
            "-m",
            "cobol_archaeologist.eval.codex_tool",
        ]
    )


def native_login_status(codex_binary: str) -> str:
    result = subprocess.run(
        [codex_binary, "login", "status"],
        capture_output=True,
        check=False,
        text=True,
        env=sanitized_codex_environment(),
    )
    status = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part)
    if result.returncode or "ChatGPT" not in status:
        raise RuntimeError(
            "native Codex must be logged in through ChatGPT; API-key auth is refused"
        )
    return status


def native_chatgpt_account_sha256(
    source_environment: Mapping[str, str] | None = None,
) -> str:
    """Hash only the stable ChatGPT account id from Codex auth state."""

    environment = sanitized_codex_environment(source_environment)
    codex_home = environment.get("CODEX_HOME")
    if codex_home is None:
        profile = environment.get("USERPROFILE") or environment.get("HOME")
        if profile is None:
            raise RuntimeError("cannot locate native Codex auth state")
        codex_home = str(Path(profile) / ".codex")
    payload = json.loads((Path(codex_home) / "auth.json").read_text(encoding="utf-8"))
    tokens = payload.get("tokens")
    account_id = tokens.get("account_id") if isinstance(tokens, dict) else None
    if payload.get("auth_mode") != "chatgpt" or not isinstance(account_id, str):
        raise RuntimeError("native Codex auth state has no ChatGPT account identity")
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()


def native_codex_version(codex_binary: str) -> str:
    result = subprocess.run(
        [codex_binary, "--version"],
        capture_output=True,
        check=False,
        text=True,
        env=sanitized_codex_environment(),
    )
    if result.returncode:
        raise RuntimeError(f"read native Codex version failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _safe_relative(name: str) -> Path:
    pure = PurePath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe materialized filename {name!r}")
    return Path(*pure.parts)


def stage_native_task(
    *,
    prompt: str,
    schema: Mapping,
    sources: Mapping[str, MaterializedSource],
    task_base: Path = DEFAULT_NATIVE_TASK_BASE,
) -> Path:
    task_root = Path(task_base) / uuid.uuid4().hex
    task_root.mkdir(parents=True)
    descriptor: dict[str, dict] = {"aliases": {}}
    (task_root / "prompt.txt").write_text(prompt, encoding="utf-8")
    (task_root / "output_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    for alias, source in sources.items():
        relative = Path("cases") / alias
        descriptor["aliases"][alias] = {"source_dir": relative.as_posix()}
        destination = task_root / relative
        destination.mkdir(parents=True)
        for filename, content in source.files.items():
            path = destination / _safe_relative(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="")
    (task_root / "descriptor.json").write_text(
        json.dumps(descriptor, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return task_root


def execute_codex_task_native(
    *,
    prompt: str,
    schema: dict,
    sources: Mapping[str, MaterializedSource],
    support_root: str,
    distro: str,
    codex_binary: str,
    model_id: str,
    reasoning_effort: str,
    timeout_s: float,
    task_base: Path = DEFAULT_NATIVE_TASK_BASE,
    runtime_source_sha256: str | None = None,
    authentication_identity_sha256: str | None = None,
    authorized_hunts: Sequence[str] = (),
) -> CodexTaskExecution:
    """Stage and run one native isolated task with all API-key routes removed."""

    del distro
    repository_root = Path(support_root).resolve()
    from cobol_archaeologist.eval.config3_live import (
        runtime_source_sha256 as hash_runtime,
    )

    actual_runtime_sha = hash_runtime(repository_root)
    if runtime_source_sha256 is None or actual_runtime_sha != runtime_source_sha256:
        raise RuntimeError("native runtime differs from the explicit frozen snapshot")
    tool_command = native_tool_command(repository_root=repository_root)
    python = Path(
        tool_command.split('"')[1]
        if tool_command.startswith('"')
        else tool_command.split()[0]
    )
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import pathlib,cobol_archaeologist.eval.codex_tool as m;"
                "print(pathlib.Path(m.__file__).resolve())"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
        env=sanitized_codex_environment(),
    )
    expected_module = (
        repository_root / "src" / "cobol_archaeologist" / "eval" / "codex_tool.py"
    ).resolve()
    if probe.returncode or Path(probe.stdout.strip()).resolve() != expected_module:
        raise RuntimeError("native bridge does not import the frozen workspace module")
    task_root = stage_native_task(
        prompt=prompt,
        schema=schema,
        sources=sources,
        task_base=task_base,
    )
    resolved_base = Path(task_base).resolve()
    resolved_task = task_root.resolve()
    if resolved_task.parent != resolved_base:
        raise RuntimeError("refusing to clean an unexpected native task directory")
    try:
        arguments = native_codex_exec_arguments(
            codex_binary=codex_binary,
            task_root=task_root,
            model_id=model_id,
            reasoning_effort=reasoning_effort,
            allow_tool_bridge=bool(sources),
        )
        request_hash = codex_request_sha256(
            prompt=prompt,
            schema=schema,
            sources=sources,
            model_id=model_id,
            reasoning_effort=reasoning_effort,
            cli_arguments=arguments,
            runtime_source_sha256=actual_runtime_sha,
            transport="native",
            authentication_identity_sha256=(
                authentication_identity_sha256
                or hashlib.sha256(b"ChatGPT-status-not-supplied").hexdigest()
            ),
            authorized_hunts=authorized_hunts,
            task_root=str(task_root),
        )
        if authentication_identity_sha256 is None:
            raise RuntimeError("Codex task requires a frozen ChatGPT account identity")
        if native_chatgpt_account_sha256() != authentication_identity_sha256:
            raise RuntimeError(
                "ChatGPT account changed before native provider invocation"
            )
        result = subprocess.run(
            arguments,
            input=prompt,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
            env=sanitized_codex_environment(),
        )
        if result.returncode:
            detail = "\n".join(part for part in (result.stderr, result.stdout) if part)
            raise RuntimeError(
                f"native Codex task failed ({result.returncode}) at {task_root}: "
                f"{detail[-4000:]}"
            )
        parsed = parse_codex_events(result.stdout)
        tool_logs, event_hash = authorize_codex_event_stream(
            parsed,
            tool_command=tool_command if sources else None,
            allowed_aliases=sources,
            allowed_hunts=authorized_hunts,
        )
        return CodexTaskExecution(
            task_root=str(task_root),
            parsed=parsed,
            stderr=result.stderr,
            final_message=parsed.final_message,
            tool_logs=tool_logs,
            request_sha256=request_hash,
            event_stream_sha256=event_hash,
            tool_logs_sha256=_canonical_hash(
                [entry.model_dump(mode="json") for entry in tool_logs]
            ),
        )
    finally:
        shutil.rmtree(resolved_task)
