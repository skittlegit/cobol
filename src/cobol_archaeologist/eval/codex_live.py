"""Batched M4 execution through ChatGPT-authenticated Codex Luna.

Only provider calls are replaced.  Materialization, baseline contexts, the
``RealToolLayer``, policy guards, verification, schema-v3 records, and scoring
remain the same implementation used by the earlier API path.  The Codex task
workspace contains only opaque aliases, detector-visible clauses/contexts, and
materialized source; benchmark labels and provenance never enter it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel

from cobol_archaeologist.eval.baselines import (
    DenseRAGContext,
    OracleSliceContext,
)
from cobol_archaeologist.eval.codex_batch import (
    AGENT_HUNTS,
    CodexBaselineEnvelope,
    CodexBatchEnvelope,
    ParsedCodexEvents,
    allocate_tokens,
    bind_submitted_response,
    finalize_agent_case,
    parse_codex_events,
    sanitized_codex_environment,
    strict_codex_schema,
    validate_agent_envelope,
    validate_baseline_envelope,
)
from cobol_archaeologist.eval.codex_tool import ToolLogEntry
from cobol_archaeologist.eval.live import (
    AGENT_BUDGET,
    BASELINE_BUDGET,
    INPUT_REVISION,
    MIN_AGENT_ABSTENTION_OBSERVATIONS,
    OUTPUT_DIR,
    ROOT,
    SCHEMA_VERSION,
    SPLIT,
    SYSTEM_IDS,
    TOOL_VERSION,
    _tool_layer,
    load_split,
    single_shot_record,
)
from cobol_archaeologist.eval.materialize import MaterializedSource, materialize
from cobol_archaeologist.eval.run import (
    RunManifest,
    assess_run_validity,
    infrastructure_failure,
    record_outcome,
    repository_commit,
    run_key,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.prompt import HUNT_PROMPTS, AgentResponse
from cobol_archaeologist.model.verify import Entailer, default_entailer
from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.schemas import DriftInstance

MODEL_ID = "gpt-5.6-luna"
REASONING_EFFORT = "low"
PROVIDER_ID = "chatgpt-codex-plus"
PROMPT_VERSION = "m4-live-codex-batch-v1"
DEFAULT_WSL_DISTRO = "Ubuntu"
DEFAULT_CODEX_BINARY = (
    "/home/deepa/.local/bin/codex-x86_64-unknown-linux-musl"
)
DEFAULT_SUPPORT_BASE = (
    "/home/deepa/.cache/cobol-archaeologist/codex-support"
)
DEFAULT_TASK_BASE = "/home/deepa/.cache/cobol-archaeologist/codex-tasks"
AGENT_BATCH_SIZE = 2
BASELINE_BATCH_SIZE = 5
SystemID = Literal["agent", "dense_rag", "oracle_slice"]
RunMode = Literal["smoke", "pilot", "full"]

PILOT_IDS: tuple[str, ...] = (
    "drift_000001",
    "drift_000002",
    "drift_000003",
    "drift_000004",
    "drift_000005",
    "drift_000006",
    "drift_000007",
    "drift_000008",
    "drift_000009",
    "drift_000010",
    "drift_068667",
    "drift_075075",
    "drift_000012",
    "drift_000019",
    "drift_000011",
    "drift_106241",
    "drift_003896",
    "drift_024882",
    "drift_016555",
    "drift_000013",
    "drift_000014",
    "drift_076481",
    "drift_255807",
    "drift_000018",
    "drift_031462",
    "drift_548537",
    "drift_046343",
    "drift_035337",
    "drift_024379",
    "drift_052199",
    "drift_000015",
    "drift_110002",
    "drift_282357",
    "drift_110022",
    "drift_063579",
    "drift_611233",
    "drift_066224",
    "drift_063888",
    "drift_157934",
    "drift_071627",
)


class CodexTaskExecution(BaseModel):
    task_root: str
    parsed: ParsedCodexEvents
    stderr: str
    final_message: str
    tool_logs: list[ToolLogEntry]


class _ReplayDecisionModel:
    """One-response DecisionModel used by the existing baseline finalizer."""

    def __init__(self, response: AgentResponse, model_id: str = MODEL_ID) -> None:
        self.response = response
        self.model_id = model_id
        self.temperature = 0.0
        self.seed = None
        self._used = False

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict],
    ) -> AgentResponse:
        if self._used:
            raise RuntimeError("batched baseline replay response already consumed")
        self._used = True
        return self.response


def _chunks[T](values: Sequence[T], size: int) -> list[list[T]]:
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


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


def _wsl(
    arguments: Sequence[str],
    *,
    distro: str,
    input_bytes: bytes | None = None,
    timeout: float = 120,
) -> subprocess.CompletedProcess[bytes]:
    command = (
        list(arguments)
        if sys.platform == "linux"
        else ["wsl", "-d", distro, "--", *arguments]
    )
    return subprocess.run(
        command,
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=sanitized_codex_environment(),
    )


def _require_ok(
    result: subprocess.CompletedProcess[bytes],
    action: str,
) -> None:
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"{action} failed ({result.returncode}): {stderr}")


def _stage_archive(
    root: str,
    files: Mapping[str, bytes],
    *,
    distro: str,
) -> None:
    made = _wsl(["mkdir", "-p", root], distro=distro)
    _require_ok(made, f"create WSL directory {root}")
    extracted = _wsl(
        ["tar", "-xf", "-", "-C", root],
        distro=distro,
        input_bytes=_tar_bytes(files),
    )
    _require_ok(extracted, f"stage WSL directory {root}")


def prepare_support_runtime(
    *,
    commit: str,
    distro: str = DEFAULT_WSL_DISTRO,
    support_base: str = DEFAULT_SUPPORT_BASE,
) -> str:
    """Build a data-free Python support environment keyed to the run commit."""

    if not commit or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError("support runtime commit must be lowercase hexadecimal")
    support_root = f"{support_base}/{commit}"
    marker = f"{support_root}/.ready"
    ready = _wsl(["test", "-f", marker], distro=distro)
    if ready.returncode == 0:
        return support_root

    files: dict[str, bytes] = {
        "pyproject.toml": (ROOT / "pyproject.toml").read_bytes(),
    }
    for path in (ROOT / "src").rglob("*.py"):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in (ROOT / "vendor" / "tree-sitter-cobol").rglob("*"):
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    _stage_archive(support_root, files, distro=distro)

    uv = "/home/deepa/.local/bin/uv"
    venv = _wsl(
        [
            uv,
            "venv",
            "--python",
            "3.12",
            "--allow-existing",
            "--seed",
            f"{support_root}/.venv",
        ],
        distro=distro,
        timeout=300,
    )
    _require_ok(venv, "create isolated WSL support venv")
    installed = _wsl(
        [
            uv,
            "pip",
            "install",
            "--python",
            f"{support_root}/.venv/bin/python",
            "-e",
            support_root,
            "setuptools>=68",
        ],
        distro=distro,
        timeout=600,
    )
    _require_ok(installed, "install isolated WSL support package")
    grammar = _wsl(
        [
            f"{support_root}/.venv/bin/python",
            "-c",
            (
                "from cobol_archaeologist.parser._grammar "
                "import get_language; get_language()"
            ),
        ],
        distro=distro,
        timeout=600,
    )
    _require_ok(grammar, "build pinned WSL COBOL grammar")
    marked = _wsl(["touch", marker], distro=distro)
    _require_ok(marked, "mark WSL support runtime ready")
    return support_root


def codex_exec_arguments(
    *,
    codex_binary: str,
    task_root: str,
    model_id: str,
    reasoning_effort: str,
) -> list[str]:
    """Return the auditable no-API-key, Luna-low Codex invocation."""

    return [
        "env",
        "-u",
        "OPENAI_API_KEY",
        "-u",
        "CODEX_API_KEY",
        "-u",
        "AZURE_OPENAI_API_KEY",
        "-u",
        "ANTHROPIC_API_KEY",
        codex_binary,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "-m",
        model_id,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema",
        f"{task_root}/output_schema.json",
        "-o",
        f"{task_root}/final.json",
        "-C",
        task_root,
        "-",
    ]


def _check_chatgpt_login(
    *,
    codex_binary: str,
    distro: str,
) -> str:
    result = _wsl([codex_binary, "login", "status"], distro=distro)
    _require_ok(result, "check Codex login")
    status = "\n".join(
        text
        for text in (
            result.stdout.decode("utf-8", errors="replace").strip(),
            result.stderr.decode("utf-8", errors="replace").strip(),
        )
        if text
    )
    if "ChatGPT" not in status:
        raise RuntimeError(
            "Codex must be logged in through ChatGPT; API-key auth is refused"
        )
    return status


def build_agent_prompt(
    cases: Sequence[dict[str, Any]],
    *,
    tool_command: str,
) -> str:
    """Build a label-free multi-hunt prompt over opaque case aliases."""

    visible = json.dumps(list(cases), ensure_ascii=False, separators=(",", ":"))
    hunt_guide = "\n".join(
        f"- {hunt}: {HUNT_PROMPTS[hunt]}" for hunt in AGENT_HUNTS
    )
    return f"""\
You are the M4 COBOL compliance agent under evaluation. Investigate every
opaque case below against its supplied regulation clause. Hidden benchmark
labels, generation history, and scoring data are not available and must not be
inferred.

For source evidence, use only this bounded real-tool command:
  {tool_command} ALIAS HUNT TOOL --arguments 'JSON_OBJECT'
Use HUNT=shared when an observation supports multiple D1-D7 hunts. Do not read
case files directly and do not inspect parent directories, git history, file
timestamps, comments-as-edit-cues, formatting discontinuities, or identifier
style. Make at most 8 tool calls per alias and obtain at least 3 successful
bounded observations per alias. Prefer read_program, grep, relevant
read_paragraph calls, and only the slice/call-graph/copybook tools needed by
the evidence.

Return exactly one result for every alias and exactly one final response for
each D1-D7 hunt. The host attaches the case identity and supplied clause to a
finding; author the remaining prediction fields, cite concrete original-source
loci, and include verifier hooks. Abstain when the class-specific evidence is incomplete.
For D1 or D5 against a clause whose current_value is composite, target_path
must name a non-composite leaf from that supplied value.
"Searched and found nothing" is D2 or abstention, never conformant.
D7 is not a default verdict: it requires positive source evidence that the implemented
literal/comparator matches the clause. D6 supplies dead_paragraph evidence and
delegates reachability to the verifier. Do not emit explanations outside the
required JSON schema.

Frozen hunt instructions:
{hunt_guide}

Evidence-hook requirements: D1 supplies a source literal and compares it with
the resolved current-value leaf; D2 supplies typed insertion lines and negative
grep, caller, callee, and slice observations; D3 supplies two read_paragraph
observations, two conflicting loci, and a static hook; D4 resolves a copybook
and names a missing/extra enum value; D5 compares typed source and clause
comparators; D6 supplies a read paragraph plus dead_paragraph; D7 uses
conformant labels with no drift lines plus positive literal/comparator evidence.

Detector-visible cases:
{visible}
"""


def build_baseline_prompt(
    system_id: SystemID,
    cases: Sequence[dict[str, Any]],
) -> str:
    if system_id not in {"dense_rag", "oracle_slice"}:
        raise ValueError("baseline prompt requires dense_rag or oracle_slice")
    visible = json.dumps(list(cases), ensure_ascii=False, separators=(",", ":"))
    return f"""\
Perform one evidence-grounded COBOL compliance classification for each opaque
case using only its supplied {system_id} context. Tools and file access are not
available. Return exactly one response per alias under the required JSON
schema. A finding must use the alias as prediction.instance_id, copy the
schema. The host attaches the case identity and visible regulation clause to a
finding; author the remaining prediction fields, cite concrete source loci from
the context, and include verifier hooks. Abstain when evidence is insufficient. Do not use
or infer hidden labels, generation provenance, mutation metadata, git history,
file timestamps, formatting, comment freshness, or identifier style.
For D1 or D5 against a clause whose current_value is composite, target_path
must name a non-composite leaf from that visible value.

Detector-visible cases:
{visible}
"""


def _stage_task(
    *,
    prompt: str,
    schema: dict[str, Any],
    sources: Mapping[str, MaterializedSource],
    distro: str,
    task_base: str,
) -> str:
    task_id = uuid.uuid4().hex
    task_root = f"{task_base}/{task_id}"
    descriptor: dict[str, Any] = {"aliases": {}}
    files: dict[str, bytes] = {
        "prompt.txt": prompt.encode(),
        "output_schema.json": json.dumps(schema, sort_keys=True).encode(),
    }
    for alias, source in sources.items():
        descriptor["aliases"][alias] = {"source_dir": f"cases/{alias}"}
        for filename, text in source.files.items():
            pure = PurePosixPath(filename)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"unsafe materialized filename {filename!r}")
            files[f"cases/{alias}/{pure.as_posix()}"] = text.encode()
    files["descriptor.json"] = json.dumps(descriptor, sort_keys=True).encode()
    _stage_archive(task_root, files, distro=distro)
    return task_root


def _read_wsl_file(path: str, *, distro: str, required: bool = True) -> str:
    result = _wsl(["cat", path], distro=distro)
    if result.returncode:
        if required:
            _require_ok(result, f"read WSL file {path}")
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def execute_codex_task(
    *,
    prompt: str,
    schema: dict[str, Any],
    sources: Mapping[str, MaterializedSource],
    support_root: str,
    distro: str = DEFAULT_WSL_DISTRO,
    task_base: str = DEFAULT_TASK_BASE,
    codex_binary: str = DEFAULT_CODEX_BINARY,
    model_id: str = MODEL_ID,
    reasoning_effort: str = REASONING_EFFORT,
    timeout_s: float = 900,
) -> CodexTaskExecution:
    """Stage and execute one isolated, replayable ChatGPT Codex task."""

    task_root = _stage_task(
        prompt=prompt,
        schema=schema,
        sources=sources,
        distro=distro,
        task_base=task_base,
    )
    arguments = codex_exec_arguments(
        codex_binary=codex_binary,
        task_root=task_root,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
    )
    result = _wsl(
        arguments,
        distro=distro,
        input_bytes=prompt.encode(),
        timeout=timeout_s,
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode:
        stdout = result.stdout.decode("utf-8", errors="replace")
        detail = "\n".join(part for part in (stderr, stdout) if part).strip()
        raise RuntimeError(
            f"Codex task failed ({result.returncode}) at {task_root}: "
            f"{detail[-4000:]}"
        )
    stdout = result.stdout.decode("utf-8", errors="replace")
    parsed = parse_codex_events(stdout)
    final_message = _read_wsl_file(
        f"{task_root}/final.json",
        distro=distro,
    ).strip()
    if not final_message:
        final_message = parsed.final_message
    log_text = _read_wsl_file(
        f"{task_root}/tool_log.jsonl",
        distro=distro,
        required=False,
    )
    tool_logs = [
        ToolLogEntry.model_validate_json(line)
        for line in log_text.splitlines()
        if line.strip()
    ]
    return CodexTaskExecution(
        task_root=task_root,
        parsed=parsed,
        stderr=stderr,
        final_message=final_message,
        tool_logs=tool_logs,
    )


def _extract_context(question: str) -> dict[str, Any]:
    marker = "Visible context (JSON):\n"
    suffix = "\nReturn one finding or abstain. Tool calls are not available."
    if marker not in question or not question.endswith(suffix):
        raise ValueError("prior baseline question has an unknown context envelope")
    return json.loads(question.split(marker, 1)[1][: -len(suffix)])


def load_reusable_baseline_contexts(
    system_id: SystemID,
    *,
    source_shas: Mapping[str, str],
    artifact_dir: Path = ROOT / "data" / "eval" / "m4",
) -> dict[str, dict[str, Any]]:
    """Reuse only deterministic, source-hash-matched contexts from API runs."""

    if system_id not in {"dense_rag", "oracle_slice"}:
        raise ValueError("only baseline contexts are reusable")
    path = Path(artifact_dir) / f"{system_id}.jsonl"
    contexts: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        instance_id = record["instance_id"]
        if record["source_sha256"] != source_shas.get(instance_id):
            continue
        trajectory = record.get("trajectory")
        if not trajectory:
            continue
        contexts[instance_id] = _extract_context(trajectory["question"])
    missing = sorted(set(source_shas) - set(contexts))
    if missing:
        raise RuntimeError(
            "reusable baseline contexts are missing or source-stale for "
            f"{len(missing)} row(s): {', '.join(missing[:3])}"
        )
    return contexts


def _mode_rows(
    rows: Sequence[DriftInstance],
    mode: RunMode,
) -> list[DriftInstance]:
    if mode == "smoke":
        return list(rows[:5])
    if mode == "pilot":
        by_id = {row.instance_id: row for row in rows}
        missing = [instance_id for instance_id in PILOT_IDS if instance_id not in by_id]
        if missing:
            raise ValueError(f"pilot IDs missing from split: {missing}")
        return [by_id[instance_id] for instance_id in PILOT_IDS]
    return list(rows)


def _assert_clean_runtime_source() -> None:
    scope = ("src/cobol_archaeologist", "pyproject.toml")
    dirty: list[str] = []
    for cached in (False, True):
        command = ["git", "diff", "--name-only", "--ignore-cr-at-eol"]
        if cached:
            command.append("--cached")
        command.extend(("--", *scope))
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
        dirty.extend(line for line in result.stdout.splitlines() if line)
    untracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            *scope,
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    dirty.extend(line for line in untracked.stdout.splitlines() if line)
    if dirty:
        raise RuntimeError(
            "Codex M4 execution requires committed runtime source; "
            "commit or remove the listed changes first:\n"
            + "\n".join(sorted(set(dirty)))
        )


def _artifact_dir(output_dir: Path, mode: RunMode) -> Path:
    return Path(output_dir) / ("smoke" if mode == "smoke" else mode)


def _manifest(
    *,
    system_id: SystemID,
    mode: RunMode,
    rows: Sequence[DriftInstance],
    commit: str,
    cli_version: str,
) -> RunManifest:
    budget = AGENT_BUDGET if system_id == "agent" else BASELINE_BUDGET
    return RunManifest(
        system_id=system_id,
        provider=PROVIDER_ID,
        model_id=MODEL_ID,
        decoding={
            "reasoning_effort": REASONING_EFFORT,
            "temperature_parameter": "not_exposed_by_codex_cli",
            "seed": None,
            "authentication": "ChatGPT",
            "codex_cli_version": cli_version,
            "batch_size": (
                AGENT_BATCH_SIZE if system_id == "agent" else BASELINE_BATCH_SIZE
            ),
            **(
                {
                    "min_successful_observations_before_abstention": (
                        MIN_AGENT_ABSTENTION_OBSERVATIONS
                    )
                }
                if system_id == "agent"
                else {}
            ),
        },
        budgets=budget.model_dump(mode="json"),
        repository_commit=commit,
        input_revision=INPUT_REVISION,
        tool_version=f"{TOOL_VERSION}@{commit}",
        prompt_version=PROMPT_VERSION,
        split_path=SPLIT.relative_to(ROOT).as_posix(),
        split_sha256=hashlib.sha256(SPLIT.read_bytes()).hexdigest(),
        schema_version=SCHEMA_VERSION,
        run_mode=mode,
        smoke_rows=5 if mode == "smoke" else None,
        total=len(rows),
    )


def _assert_prerequisite(
    expected: RunManifest,
    *,
    output_dir: Path,
    mode: Literal["smoke", "pilot"],
) -> None:
    path = _artifact_dir(output_dir, mode) / f"{expected.system_id}.manifest.json"
    if not path.exists():
        raise RuntimeError(f"{mode} prerequisite is missing: {path}")
    prior = RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    fields = (
        "system_id",
        "provider",
        "model_id",
        "decoding",
        "budgets",
        "repository_commit",
        "input_revision",
        "tool_version",
        "prompt_version",
        "split_path",
        "split_sha256",
        "schema_version",
    )
    mismatches = [
        field for field in fields if getattr(prior, field) != getattr(expected, field)
    ]
    required_total = 5 if mode == "smoke" else len(PILOT_IDS)
    valid = (
        prior.run_mode == mode
        and prior.total == required_total
        and len(prior.completed_run_keys) == required_total
        and not prior.infrastructure_failures
        and prior.validity is not None
        and prior.validity.status == "VALID"
        and prior.validity.completed_rows == required_total
    )
    if mismatches or not valid:
        detail = (
            f"mismatched fields: {', '.join(mismatches)}"
            if mismatches
            else "manifest is incomplete or not VALID"
        )
        raise RuntimeError(f"{mode} prerequisite failed: {detail}")


def _key(
    row: DriftInstance,
    source: MaterializedSource,
    *,
    system_id: SystemID,
    manifest: RunManifest,
) -> str:
    return run_key(
        instance_id=row.instance_id,
        source_sha256=source.source_sha256,
        system_id=system_id,
        model_id=manifest.model_id,
        budgets=manifest.budgets,
        prompt_version=manifest.prompt_version,
        tool_version=manifest.tool_version,
        commit=manifest.repository_commit,
        schema_version=manifest.schema_version,
    )


def _load_existing(path: Path) -> dict[str, EvaluationRecord]:
    if not path.exists():
        return {}
    records = [
        EvaluationRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_key = {record.run_key: record for record in records}
    if len(by_key) != len(records):
        raise ValueError(f"{path} contains duplicate run keys")
    return by_key


def _write_manifest(
    manifest: RunManifest,
    records: Sequence[EvaluationRecord],
    path: Path,
) -> None:
    manifest.completed_run_keys = sorted(record.run_key for record in records)
    manifest.infrastructure_failures = {
        record.instance_id: record.infrastructure_error
        for record in records
        if record.infrastructure_error
    }
    manifest.validity = assess_run_validity(records, system_id=manifest.system_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def _persist_raw(
    execution: CodexTaskExecution,
    *,
    artifact_dir: Path,
    system_id: SystemID,
    batch_index: int,
) -> None:
    raw_dir = artifact_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{system_id}-{batch_index:04d}"
    (raw_dir / f"{stem}.events.jsonl").write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in execution.parsed.events)
        + "\n",
        encoding="utf-8",
    )
    (raw_dir / f"{stem}.meta.json").write_text(
        json.dumps(
            {
                "task_root": execution.task_root,
                "usage": execution.parsed.usage.model_dump(mode="json"),
                "thread_id": execution.parsed.thread_id,
                "stderr": execution.stderr,
                "tool_calls": len(execution.tool_logs),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def run_codex_system(
    system_id: SystemID,
    *,
    rows: Sequence[DriftInstance],
    mode: RunMode,
    output_dir: Path = OUTPUT_DIR / "chatgpt-luna",
    entailer: Entailer | None = None,
    regulation_search: RegulationSearch | None = None,
    distro: str = DEFAULT_WSL_DISTRO,
    codex_binary: str = DEFAULT_CODEX_BINARY,
) -> list[EvaluationRecord]:
    """Run one resumable M4 system with fresh Luna outputs and trusted guards."""

    if system_id not in SYSTEM_IDS:
        raise ValueError(f"unknown M4 system {system_id!r}")
    _assert_clean_runtime_source()
    run_rows = _mode_rows(rows, mode)
    commit = repository_commit(ROOT)
    support_root = prepare_support_runtime(commit=commit, distro=distro)
    login = _check_chatgpt_login(codex_binary=codex_binary, distro=distro)
    version_result = _wsl([codex_binary, "--version"], distro=distro)
    _require_ok(version_result, "read Codex CLI version")
    cli_version = version_result.stdout.decode("utf-8", errors="replace").strip()
    if "ChatGPT" not in login:
        raise RuntimeError("ChatGPT Codex login check failed")

    manifest = _manifest(
        system_id=system_id,
        mode=mode,
        rows=run_rows,
        commit=commit,
        cli_version=cli_version,
    )
    if mode in {"pilot", "full"}:
        _assert_prerequisite(
            manifest,
            output_dir=Path(output_dir),
            mode="smoke",
        )
    if mode == "full":
        _assert_prerequisite(
            manifest,
            output_dir=Path(output_dir),
            mode="pilot",
        )
    materialized = {row.instance_id: materialize(row) for row in run_rows}
    source_shas = {
        instance_id: source.source_sha256
        for instance_id, source in materialized.items()
    }
    contexts = (
        load_reusable_baseline_contexts(
            system_id,
            source_shas=source_shas,
        )
        if system_id != "agent"
        else {}
    )
    artifact_dir = _artifact_dir(Path(output_dir), mode)
    records_path = artifact_dir / f"{system_id}.jsonl"
    manifest_path = artifact_dir / f"{system_id}.manifest.json"
    existing = _load_existing(records_path)
    records: list[EvaluationRecord] = []
    pending: list[DriftInstance] = []
    keys: dict[str, str] = {}
    for row in run_rows:
        key = _key(
            row,
            materialized[row.instance_id],
            system_id=system_id,
            manifest=manifest,
        )
        keys[row.instance_id] = key
        if key in existing:
            records.append(existing[key])
        else:
            pending.append(row)

    batch_size = AGENT_BATCH_SIZE if system_id == "agent" else BASELINE_BATCH_SIZE
    entailer = entailer or default_entailer()
    records_path.parent.mkdir(parents=True, exist_ok=True)
    with records_path.open("a", encoding="utf-8", newline="\n") as stream:
        for batch_index, batch in enumerate(
            _chunks(pending, batch_size),
            start=1,
        ):
            aliases = [
                f"drift_{900000 + index:06d}"
                for index in range(len(batch))
            ]
            alias_rows = dict(zip(aliases, batch, strict=True))
            try:
                if system_id == "agent":
                    visible = [
                        {
                            "alias": alias,
                            "program_scope": (
                                Path(row.provenance.base_program).stem
                            ),
                            "clause": row.regulation_clause.model_dump(mode="json"),
                        }
                        for alias, row in alias_rows.items()
                    ]
                    tool_command = (
                        f"{support_root}/.venv/bin/python -m "
                        "cobol_archaeologist.eval.codex_tool"
                    )
                    prompt = build_agent_prompt(
                        visible,
                        tool_command=tool_command,
                    )
                    execution = execute_codex_task(
                        prompt=prompt,
                        schema=strict_codex_schema(CodexBatchEnvelope),
                        sources={
                            alias: materialized[row.instance_id]
                            for alias, row in alias_rows.items()
                        },
                        support_root=support_root,
                        distro=distro,
                        codex_binary=codex_binary,
                    )
                    _persist_raw(
                        execution,
                        artifact_dir=artifact_dir,
                        system_id=system_id,
                        batch_index=batch_index,
                    )
                    envelope = CodexBatchEnvelope.model_validate_json(
                        execution.final_message
                    )
                    validate_agent_envelope(envelope, aliases)
                    by_alias = {result.alias: result for result in envelope.results}
                    allocations = allocate_tokens(
                        execution.parsed.usage.total_tokens,
                        len(batch) * len(AGENT_HUNTS),
                    )
                    batch_records: list[EvaluationRecord] = []
                    for row_index, (alias, row) in enumerate(alias_rows.items()):
                        source = materialized[row.instance_id]
                        with tempfile.TemporaryDirectory(
                            prefix="m4-codex-verify-"
                        ) as temp:
                            tools = _tool_layer(
                                source,
                                Path(temp),
                                regulation_search,
                            )
                            start = row_index * len(AGENT_HUNTS)
                            outcome = finalize_agent_case(
                                by_alias[alias],
                                clause=row.regulation_clause,
                                program_scope=Path(
                                    row.provenance.base_program
                                ).stem,
                                instance_id=row.instance_id,
                                logs=[
                                    log
                                    for log in execution.tool_logs
                                    if log.alias == alias
                                ],
                                tools=tools,
                                budget=AGENT_BUDGET,
                                entailer=entailer,
                                token_counts=allocations[
                                    start : start + len(AGENT_HUNTS)
                                ],
                                min_successful_observations=(
                                    MIN_AGENT_ABSTENTION_OBSERVATIONS
                                ),
                                model_id=MODEL_ID,
                            )
                        batch_records.append(
                            record_outcome(
                                row,
                                outcome,
                                system_id=system_id,
                                source_sha256=source.source_sha256,
                                key=keys[row.instance_id],
                            )
                        )
                else:
                    visible = [
                        {
                            "alias": alias,
                            "context": contexts[row.instance_id],
                        }
                        for alias, row in alias_rows.items()
                    ]
                    prompt = build_baseline_prompt(system_id, visible)
                    execution = execute_codex_task(
                        prompt=prompt,
                        schema=strict_codex_schema(CodexBaselineEnvelope),
                        sources={},
                        support_root=support_root,
                        distro=distro,
                        codex_binary=codex_binary,
                    )
                    _persist_raw(
                        execution,
                        artifact_dir=artifact_dir,
                        system_id=system_id,
                        batch_index=batch_index,
                    )
                    envelope = CodexBaselineEnvelope.model_validate_json(
                        execution.final_message
                    )
                    validate_baseline_envelope(envelope, aliases)
                    by_alias = {result.alias: result for result in envelope.results}
                    allocations = allocate_tokens(
                        execution.parsed.usage.total_tokens,
                        len(batch),
                    )
                    batch_records = []
                    for token_count, (alias, row) in zip(
                        allocations,
                        alias_rows.items(),
                        strict=True,
                    ):
                        source = materialized[row.instance_id]
                        response = bind_submitted_response(
                            by_alias[alias].response,
                            instance_id=row.instance_id,
                            clause=row.regulation_clause,
                            token_count=token_count,
                        )
                        with tempfile.TemporaryDirectory(
                            prefix="m4-codex-verify-"
                        ) as temp:
                            tools = _tool_layer(
                                source,
                                Path(temp),
                                regulation_search,
                            )
                            context = (
                                DenseRAGContext.model_validate(
                                    contexts[row.instance_id]
                                )
                                if system_id == "dense_rag"
                                else OracleSliceContext.model_validate(
                                    contexts[row.instance_id]
                                )
                            )
                            batch_records.append(
                                single_shot_record(
                                    row,
                                    system_id=system_id,
                                    source_sha256=source.source_sha256,
                                    key=keys[row.instance_id],
                                    context=context,
                                    tools=tools,
                                    model_factory=lambda response=response: (
                                        _ReplayDecisionModel(response)
                                    ),
                                    entailer=entailer,
                                )
                            )
            except Exception as exc:  # noqa: BLE001
                batch_records = [
                    infrastructure_failure(
                        row,
                        system_id=system_id,
                        source_sha256=materialized[row.instance_id].source_sha256,
                        key=keys[row.instance_id],
                        reason=(
                            "Codex batch failed: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )
                    for row in batch
                ]

            for record in batch_records:
                stream.write(record.model_dump_json() + "\n")
                stream.flush()
                records.append(record)
            records.sort(
                key=lambda record: next(
                    index
                    for index, row in enumerate(run_rows)
                    if row.instance_id == record.instance_id
                )
            )
            _write_manifest(manifest, records, manifest_path)
            print(
                json.dumps(
                    {
                        "system": system_id,
                        "mode": mode,
                        "completed": len(records),
                        "total": len(run_rows),
                        "validity": manifest.validity.status,
                        "infrastructure_failures": len(
                            manifest.infrastructure_failures
                        ),
                    }
                ),
                flush=True,
            )
            if manifest.validity.status == "HALTED_CONTRACT_REJECTIONS":
                break
    _write_manifest(manifest, records, manifest_path)
    return records


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--system",
        choices=(*SYSTEM_IDS, "all"),
        default="all",
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "pilot", "full"),
        default="smoke",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = load_split()
    entailer = default_entailer()
    systems = SYSTEM_IDS if args.system == "all" else (args.system,)
    for system_id in systems:
        run_codex_system(
            system_id,
            rows=rows,
            mode=args.mode,
            entailer=entailer,
            regulation_search=None,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
