"""Immutable, task-keyed source staging for collaboration subagents.

Configuration-3 collaboration workers share one repository checkout.  Their
opaque aliases therefore cannot be staged in the checkout root without races.
This module gives every frozen ``run_key`` its own immutable source tree and a
bounded command whose tool transcript is maintained by the host as a hash
chain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.loop import _summarize
from cobol_archaeologist.eval.codex_batch import AGENT_HUNTS
from cobol_archaeologist.eval.codex_tool import (
    ADAPTIVE_HUNT,
    MAX_ADAPTIVE_TOOL_CALLS,
    MAX_TOOL_CALLS_PER_HUNT,
    ToolLogEntry,
    ToolRequest,
)
from cobol_archaeologist.eval.materialize import MaterializedSource
from cobol_archaeologist.tool_types import RunInputs, ToolLayer
from cobol_archaeologist.tools import RealToolLayer

STAGING_SCHEMA = "configuration-3-collaboration-staging-v1"
TOOL_RECORD_SCHEMA = "configuration-3-collaboration-tool-record-v1"
DESCRIPTOR_NAME = "descriptor.json"
MANIFEST_NAME = "staging-manifest.json"
TOOL_LOG_NAME = "host-tool-log.jsonl"
LOCK_NAME = ".host-tool-log.lock"
_RUN_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_ALIAS_RE = re.compile(r"^drift_9\d{5}$")
_ZERO_HASH = "0" * 64
_ROOT = Path(__file__).resolve().parents[3]
_FROZEN_CONFIG4_STAGING = Path(
    "data/eval/m4-config4/lineage-v2/train-dev/adaptive_agent/task-staging-v1"
)
_CANONICAL_CONFIG4_STAGING = Path(
    "data/eval/m4/lineage/train-dev/adaptive_agent/task-staging"
)


def _canonical_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def tool_log_entry_sha256(entry: ToolLogEntry) -> str:
    """Canonical hash used by host-captured ``tool.completed`` events."""

    return _sha256(_canonical_bytes(entry))


def _safe_relative_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe staged relative path {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe staged relative path {value!r}")
    normalized = pure.as_posix()
    if normalized != value or ":" in pure.parts[0]:
        raise ValueError(f"unsafe staged relative path {value!r}")
    return normalized


def _task_root(staging_base: Path, run_key: str) -> Path:
    if not _RUN_KEY_RE.fullmatch(run_key):
        raise ValueError("collaboration staging run_key must be 64 lowercase hex chars")
    base = Path(staging_base).resolve()
    target = base / run_key
    resolved_target = target.resolve()
    if resolved_target == base or base not in resolved_target.parents:
        raise ValueError("collaboration staging task root escapes staging base")
    return target


def _resolve_cli_staging_base(staging_base: Path, *, root: Path = _ROOT) -> Path:
    """Map the one frozen config-4 prompt path after canonical promotion.

    The 102 already-signed Luna requests must keep their exact prompt bytes.
    Their tool command names the pre-promotion staging directory, so the CLI
    accepts only that exact missing path and redirects it to the canonical M4
    tree. All other paths retain the ordinary fail-closed behavior.
    """

    root = Path(root).resolve()
    supplied = Path(staging_base).resolve()
    if supplied.exists():
        return supplied
    try:
        relative = supplied.relative_to(root)
    except ValueError:
        return supplied
    if relative.as_posix().lower() != _FROZEN_CONFIG4_STAGING.as_posix().lower():
        return supplied
    canonical = (root / _CANONICAL_CONFIG4_STAGING).resolve()
    return canonical if canonical.is_dir() else supplied


class StagedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CollaborationStagingManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = STAGING_SCHEMA
    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    staging_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[StagedFile, ...]

    @model_validator(mode="after")
    def _paths_are_canonical(self) -> CollaborationStagingManifest:
        paths = [row.path for row in self.files]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("staging manifest paths are not unique and sorted")
        for path in paths:
            _safe_relative_path(path)
        return self


class ChainedToolLogRecord(BaseModel):
    """One ToolLogEntry payload bound to its task and preceding record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = TOOL_RECORD_SCHEMA
    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    staging_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence: int = Field(ge=1)
    previous_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry: ToolLogEntry
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _record_hash_is_exact(self) -> ChainedToolLogRecord:
        if self.entry.sequence != self.sequence:
            raise ValueError("chained tool record and ToolLogEntry sequence differ")
        expected = _tool_record_sha256(
            run_key=self.run_key,
            staging_sha256=self.staging_sha256,
            sequence=self.sequence,
            previous_sha256=self.previous_sha256,
            entry=self.entry,
        )
        if self.record_sha256 != expected:
            raise ValueError("chained tool record hash differs from exact payload")
        return self


class StagedCollaborationTask(BaseModel):
    """Host-facing identity for one immutable staged task."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    task_root: Path
    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    staging_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_command: str = Field(min_length=1)


def _staging_manifest(
    run_key: str, files: Mapping[str, bytes]
) -> CollaborationStagingManifest:
    rows = tuple(
        StagedFile(path=path, size=len(payload), sha256=_sha256(payload))
        for path, payload in sorted(files.items())
    )
    identity = {
        "schema_version": STAGING_SCHEMA,
        "run_key": run_key,
        "files": [row.model_dump(mode="json") for row in rows],
    }
    return CollaborationStagingManifest(
        run_key=run_key,
        staging_sha256=_sha256(_canonical_bytes(identity)),
        files=rows,
    )


def _descriptor_bytes(
    *,
    run_key: str,
    sources: Mapping[str, MaterializedSource],
    authorized_hunts: Sequence[str],
) -> bytes:
    aliases = {
        alias: {
            "main_file": source.main_file,
            "source_dir": f"cases/{alias}",
            "source_sha256": source.source_sha256,
        }
        for alias, source in sorted(sources.items())
    }
    return _canonical_bytes(
        {
            "schema_version": STAGING_SCHEMA,
            "run_key": run_key,
            "authorized_hunts": list(authorized_hunts),
            "aliases": aliases,
        }
    )


def _staged_files(
    *,
    run_key: str,
    sources: Mapping[str, MaterializedSource],
    authorized_hunts: Sequence[str],
) -> dict[str, bytes]:
    if not sources:
        raise ValueError("collaboration tool staging requires at least one source")
    allowed_hunts = {*AGENT_HUNTS, ADAPTIVE_HUNT}
    if (
        not authorized_hunts
        or len(authorized_hunts) != len(set(authorized_hunts))
        or any(hunt not in allowed_hunts for hunt in authorized_hunts)
    ):
        raise ValueError("collaboration staging contains invalid authorized hunts")
    files = {
        DESCRIPTOR_NAME: _descriptor_bytes(
            run_key=run_key,
            sources=sources,
            authorized_hunts=authorized_hunts,
        )
    }
    for alias, source in sorted(sources.items()):
        if not _ALIAS_RE.fullmatch(alias):
            raise ValueError(f"unsafe or unsupported collaboration alias {alias!r}")
        main_file = _safe_relative_path(source.main_file)
        source_names = {_safe_relative_path(name) for name in source.files}
        if main_file not in source_names:
            raise ValueError(f"main source file {main_file!r} is not materialized")
        for name, content in sorted(source.files.items()):
            relative = _safe_relative_path(name)
            path = f"cases/{alias}/{relative}"
            if path in files:
                raise ValueError(f"duplicate staged relative path {path!r}")
            files[path] = content.encode("utf-8")
    return files


def _write_new_staging(
    task_root: Path,
    *,
    files: Mapping[str, bytes],
    manifest: CollaborationStagingManifest,
) -> None:
    task_root.mkdir(parents=False, exist_ok=False)
    for relative, payload in sorted(files.items()):
        target = task_root / Path(*PurePosixPath(relative).parts)
        resolved = target.resolve()
        if task_root not in resolved.parents:
            raise ValueError(f"staged path escapes task root: {relative!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    with (task_root / MANIFEST_NAME).open(
        "x", encoding="utf-8", newline="\n"
    ) as stream:
        stream.write(manifest.model_dump_json(indent=2))
        stream.flush()
        os.fsync(stream.fileno())


def _verify_staging(
    task_root: Path,
    *,
    manifest: CollaborationStagingManifest,
    expected_files: Mapping[str, bytes] | None = None,
) -> None:
    if task_root.is_symlink() or not task_root.is_dir():
        raise ValueError("collaboration staging task root is not a real directory")
    resolved_root = task_root.resolve()
    manifest_path = task_root / MANIFEST_NAME
    on_disk = CollaborationStagingManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if on_disk != manifest:
        raise RuntimeError("existing collaboration staging manifest is nonidentical")
    expected_paths = {row.path for row in manifest.files}
    actual_paths: set[str] = set()
    for root_name in (DESCRIPTOR_NAME, "cases"):
        root_path = task_root / root_name
        candidates = [root_path] if root_path.is_file() else list(root_path.rglob("*"))
        for path in candidates:
            if path.is_symlink():
                raise ValueError(
                    f"symlink is forbidden in collaboration staging: {path}"
                )
            if path.is_file():
                actual_paths.add(path.relative_to(task_root).as_posix())
    if actual_paths != expected_paths:
        raise RuntimeError("collaboration staging immutable path set changed")
    rows = {row.path: row for row in manifest.files}
    for relative in sorted(expected_paths):
        path = task_root / Path(*PurePosixPath(relative).parts)
        resolved = path.resolve()
        if resolved_root not in resolved.parents:
            raise ValueError(f"staged path escapes task root: {relative!r}")
        payload = path.read_bytes()
        row = rows[relative]
        if len(payload) != row.size or _sha256(payload) != row.sha256:
            raise RuntimeError(f"collaboration staging byte mismatch: {relative}")
        if expected_files is not None and payload != expected_files[relative]:
            raise RuntimeError(
                f"existing collaboration staging bytes differ: {relative}"
            )


def collaboration_tool_command(
    *,
    staging_base: Path,
    run_key: str,
    staging_sha256: str,
    python_executable: str | Path | None = None,
) -> str:
    """Return the exact bounded-command prefix for one staged task."""

    _task_root(staging_base, run_key)
    if not re.fullmatch(r"[0-9a-f]{64}", staging_sha256):
        raise ValueError("invalid collaboration staging hash")
    python = Path(python_executable or sys.executable).resolve()
    return subprocess.list2cmdline(
        [
            str(python),
            "-m",
            "cobol_archaeologist.eval.collaboration_staging",
            "--staging-base",
            str(Path(staging_base).resolve()),
            "--run-key",
            run_key,
            "--staging-sha256",
            staging_sha256,
        ]
    )


def stage_collaboration_task(
    *,
    staging_base: Path,
    run_key: str,
    sources: Mapping[str, MaterializedSource],
    authorized_hunts: Sequence[str],
    python_executable: str | Path | None = None,
) -> StagedCollaborationTask:
    """Create one immutable task tree, or verify byte-identical resume state."""

    task_root = _task_root(staging_base, run_key)
    files = _staged_files(
        run_key=run_key,
        sources=sources,
        authorized_hunts=authorized_hunts,
    )
    manifest = _staging_manifest(run_key, files)
    task_root.parent.mkdir(parents=True, exist_ok=True)
    if task_root.exists():
        _verify_staging(task_root, manifest=manifest, expected_files=files)
    else:
        _write_new_staging(task_root, files=files, manifest=manifest)
        _verify_staging(task_root, manifest=manifest, expected_files=files)
    return StagedCollaborationTask(
        task_root=task_root,
        run_key=run_key,
        staging_sha256=manifest.staging_sha256,
        tool_command=collaboration_tool_command(
            staging_base=staging_base,
            run_key=run_key,
            staging_sha256=manifest.staging_sha256,
            python_executable=python_executable,
        ),
    )


def load_staging_manifest(
    *, staging_base: Path, run_key: str, expected_staging_sha256: str
) -> CollaborationStagingManifest:
    task_root = _task_root(staging_base, run_key)
    manifest = CollaborationStagingManifest.model_validate_json(
        (task_root / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    if (
        manifest.run_key != run_key
        or manifest.staging_sha256 != expected_staging_sha256
    ):
        raise ValueError("collaboration staging identity differs from bounded command")
    _verify_staging(task_root, manifest=manifest)
    return manifest


def _tool_record_sha256(
    *,
    run_key: str,
    staging_sha256: str,
    sequence: int,
    previous_sha256: str,
    entry: ToolLogEntry,
) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "schema_version": TOOL_RECORD_SCHEMA,
                "run_key": run_key,
                "staging_sha256": staging_sha256,
                "sequence": sequence,
                "previous_sha256": previous_sha256,
                "entry": entry.model_dump(mode="json"),
            }
        )
    )


def _descriptor(task_root: Path) -> dict[str, Any]:
    payload = json.loads((task_root / DESCRIPTOR_NAME).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("collaboration staging descriptor is not an object")
    return payload


def load_staged_tool_records(
    *, staging_base: Path, run_key: str, expected_staging_sha256: str
) -> tuple[ChainedToolLogRecord, ...]:
    """Validate the immutable stage and complete host-owned tool hash chain."""

    load_staging_manifest(
        staging_base=staging_base,
        run_key=run_key,
        expected_staging_sha256=expected_staging_sha256,
    )
    task_root = _task_root(staging_base, run_key)
    descriptor = _descriptor(task_root)
    aliases = descriptor.get("aliases")
    hunts = descriptor.get("authorized_hunts")
    if not isinstance(aliases, dict) or not isinstance(hunts, list):
        raise TypeError("collaboration staging descriptor is malformed")
    path = task_root / TOOL_LOG_NAME
    if not path.exists():
        return ()
    records: list[ChainedToolLogRecord] = []
    previous = _ZERO_HASH
    for expected_sequence, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line:
            raise ValueError("host-owned collaboration tool log contains a blank line")
        record = ChainedToolLogRecord.model_validate_json(line)
        if (
            record.run_key != run_key
            or record.staging_sha256 != expected_staging_sha256
            or record.sequence != expected_sequence
            or record.previous_sha256 != previous
            or record.entry.alias not in aliases
            or record.entry.hunt not in hunts
        ):
            raise ValueError("host-owned collaboration tool log chain is invalid")
        records.append(record)
        previous = record.record_sha256
    return tuple(records)


def load_staged_tool_logs(
    *, staging_base: Path, run_key: str, expected_staging_sha256: str
) -> tuple[ToolLogEntry, ...]:
    return tuple(
        row.entry
        for row in load_staged_tool_records(
            staging_base=staging_base,
            run_key=run_key,
            expected_staging_sha256=expected_staging_sha256,
        )
    )


@contextmanager
def _tool_log_lock(task_root: Path, timeout_s: float = 10.0):
    lock_path = task_root / LOCK_NAME
    deadline = time.monotonic() + timeout_s
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError("timed out acquiring host tool-log lock") from None
            time.sleep(0.01)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def execute_staged_tool_request(
    request: ToolRequest,
    *,
    staging_base: Path,
    run_key: str,
    expected_staging_sha256: str,
    tool_factory: Callable[[Path], ToolLayer] = lambda source: RealToolLayer(
        corpus_root=source,
        copybook_paths=[source],
    ),
) -> ChainedToolLogRecord:
    """Execute and append one authorized ToolLogEntry as a chained host record."""

    task_root = _task_root(staging_base, run_key)
    with _tool_log_lock(task_root):
        records = load_staged_tool_records(
            staging_base=staging_base,
            run_key=run_key,
            expected_staging_sha256=expected_staging_sha256,
        )
        descriptor = _descriptor(task_root)
        aliases = descriptor["aliases"]
        hunts = descriptor["authorized_hunts"]
        if request.alias not in aliases:
            raise ValueError(f"unauthorized collaboration alias {request.alias!r}")
        if request.hunt not in hunts:
            raise ValueError(f"unauthorized collaboration hunt {request.hunt!r}")
        maximum = (
            MAX_ADAPTIVE_TOOL_CALLS
            if request.hunt == ADAPTIVE_HUNT
            else MAX_TOOL_CALLS_PER_HUNT
        )
        if (
            sum(
                row.entry.alias == request.alias and row.entry.hunt == request.hunt
                for row in records
            )
            >= maximum
        ):
            raise RuntimeError(
                f"tool budget exhausted for {request.alias}/{request.hunt}: "
                f"maximum {maximum} calls"
            )
        source_dir = task_root / Path(
            *PurePosixPath(aliases[request.alias]["source_dir"]).parts
        )
        resolved_source = source_dir.resolve()
        if (
            task_root.resolve() not in resolved_source.parents
            or not resolved_source.is_dir()
        ):
            raise ValueError(
                "collaboration descriptor source directory escapes task root"
            )
        tools = tool_factory(resolved_source)
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
        sequence = len(records) + 1
        entry = ToolLogEntry(
            alias=request.alias,
            hunt=request.hunt,
            sequence=sequence,
            tool=request.tool,
            arguments=request.arguments,
            observation_summary=summary,
            observation_truncated=truncated,
            error=error,
            latency_ms=latency_ms,
        )
        previous = records[-1].record_sha256 if records else _ZERO_HASH
        record = ChainedToolLogRecord(
            run_key=run_key,
            staging_sha256=expected_staging_sha256,
            sequence=sequence,
            previous_sha256=previous,
            entry=entry,
            record_sha256=_tool_record_sha256(
                run_key=run_key,
                staging_sha256=expected_staging_sha256,
                sequence=sequence,
                previous_sha256=previous,
                entry=entry,
            ),
        )
        log_path = task_root / TOOL_LOG_NAME
        with log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record.model_dump_json() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-base", required=True)
    parser.add_argument("--run-key", required=True)
    parser.add_argument("--staging-sha256", required=True)
    parser.add_argument("alias")
    parser.add_argument("hunt", choices=(*AGENT_HUNTS, ADAPTIVE_HUNT))
    parser.add_argument("tool")
    parser.add_argument("--arguments", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        request = ToolRequest(
            alias=args.alias,
            hunt=args.hunt,
            tool=args.tool,
            arguments=json.loads(args.arguments),
        )
        record = execute_staged_tool_request(
            request,
            staging_base=_resolve_cli_staging_base(Path(args.staging_base)),
            run_key=args.run_key,
            expected_staging_sha256=args.staging_sha256,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"infrastructure_error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            )
        )
        return 2
    entry = record.entry
    print(
        json.dumps(
            {
                "tool": entry.tool,
                "sequence": entry.sequence,
                "observation_summary": entry.observation_summary,
                "observation_sha256": _sha256(
                    entry.observation_summary.encode("utf-8")
                ),
                "observation_truncated": entry.observation_truncated,
                "error": entry.error,
                "tool_log_sha256": tool_log_entry_sha256(entry),
                "record_sha256": record.record_sha256,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
