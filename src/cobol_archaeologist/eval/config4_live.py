"""Governed identity and smoke gating for the numbered configuration-4 successor.

Configuration 4 is deliberately represented by a separate model and artifact
root.  The configuration-3 freeze remains loadable as its historical schema;
none of its fields are widened in place and no configuration-4 writer accepts
the configuration-3 output tree.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.eval.config3_live import (
    CONFIG3_SYSTEMS,
    ROOT,
    Config3RunFreeze,
    FinalizedArtifactPin,
    canonical_sha256,
)

CONFIG4_PROMPT_VERSION = "m4-config4-adaptive-v1"
CONFIG4_OUTPUT_DIR = ROOT / "data" / "eval" / "m4"
CONFIG4_FREEZE_PATH = CONFIG4_OUTPUT_DIR / "run-freeze.json"
CONFIG4_PREDECLARATION_PATH = CONFIG4_OUTPUT_DIR / "predeclaration.json"
CONFIG4_SMOKE_DIRECTORY = "smoke"
CONFIG4_FULL_DIRECTORY = "full"
CONFIG4_SYSTEMS = CONFIG3_SYSTEMS

Config4SystemID = Literal[
    "agent",
    "adaptive_agent",
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
]
Config4RunMode = Literal["smoke", "full"]

_HASH_PATTERN = r"^[0-9a-f]{64}$"


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def config4_prompt_sha256(prompt: str) -> str:
    """Hash the exact UTF-8 prompt bytes that a successor task will see."""

    if not prompt:
        raise ValueError("configuration-4 prompt must not be empty")
    return _sha_text(prompt)


def _path_text(path: Path | str, *, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_path(path: Path | str, *, root: Path = ROOT) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _is_config3_output(path: Path | str, *, root: Path = ROOT) -> bool:
    historical = (
        Path(root) / "data" / "eval" / "legacy" / "m4-config3"
    ).resolve()
    candidate = _resolve_path(path, root=root)
    return candidate == historical or historical in candidate.parents


def _guard_config4_output(path: Path | str, *, root: Path = ROOT) -> None:
    if _is_config3_output(path, root=root):
        raise ValueError(
            "configuration-4 artifacts cannot be written under the "
            "configuration-3 output directory"
        )


def _is_child(path: Path | str, parent: Path | str, *, root: Path = ROOT) -> bool:
    try:
        _resolve_path(path, root=root).relative_to(_resolve_path(parent, root=root))
    except ValueError:
        return False
    return True


def _method_identity_payload(
    *,
    prompt_version: str,
    prompt_sha256: str,
    prompt_hashes: Mapping[str, str],
    response_schema_sha256: str,
    response_schema_hashes: Mapping[str, str],
    tool_policy_sha256: str,
    verifier_sha256: str,
    runner_sha256: str,
) -> dict[str, Any]:
    return {
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "prompt_hashes": dict(prompt_hashes),
        "response_schema_sha256": response_schema_sha256,
        "response_schema_hashes": dict(response_schema_hashes),
        "tool_policy_sha256": tool_policy_sha256,
        "verifier_sha256": verifier_sha256,
        "runner_sha256": runner_sha256,
    }


class Config4RunFreeze(BaseModel):
    """Complete successor identity sealed before a configuration-4 call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-run-freeze-v1"] = (
        "configuration-4-run-freeze-v1"
    )
    configuration: Literal[4] = 4
    predecessor_configuration: Literal[3] = 3
    predecessor_freeze_sha256: str = Field(pattern=_HASH_PATTERN)
    provider: Literal["collaboration_subagent", "chatgpt-codex"]
    authentication: Literal["in_product_orchestration", "ChatGPT"]
    model_id: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["max"] = "max"
    prompt_version: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=_HASH_PATTERN)
    prompt_hashes: dict[str, str]
    response_schema_sha256: str = Field(pattern=_HASH_PATTERN)
    response_schema_hashes: dict[str, str]
    tool_policy_sha256: str = Field(pattern=_HASH_PATTERN)
    verifier_sha256: str = Field(pattern=_HASH_PATTERN)
    runner_sha256: str = Field(pattern=_HASH_PATTERN)
    method_identity_sha256: str = Field(pattern=_HASH_PATTERN)
    repository_commit: str
    runtime_source_sha256: str = Field(pattern=_HASH_PATTERN)
    codex_cli_version: str | None = None
    wsl_distribution: str | None = None
    transport: Literal["collaboration_subagent", "wsl", "native"]
    codex_binary: str | None = None
    max_workers: int = Field(ge=1)
    systems: tuple[Config4SystemID, ...]
    budgets: dict[str, dict[str, Any]]
    batch_sizes: dict[str, int]
    identity_hashes: dict[str, str]
    phase5_baseline_sha256: dict[str, str]
    phase5_aggregate_sha256: dict[str, str]
    chatgpt_account_sha256: str | None = Field(
        default=None, pattern=_HASH_PATTERN
    )
    decision_bootstrap_resamples: Literal[10_000] = 10_000
    decision_randomization_samples: Literal[20_000] = 20_000
    decision_statistics_seed: Literal[20_260_823] = 20_260_823
    dev_split_path: str
    dev_split_sha256: str = Field(pattern=_HASH_PATTERN)
    train_split_path: str
    train_split_sha256: str = Field(pattern=_HASH_PATTERN)
    test_split_path: str
    test_split_sha256: str = Field(pattern=_HASH_PATTERN)
    t6_v2_path: str
    t6_v2_sha256: str = Field(pattern=_HASH_PATTERN)
    smoke_seed: int
    smoke_instance_ids: tuple[str, ...] = Field(min_length=14, max_length=14)
    dev_order: tuple[str, ...]
    test_order: tuple[str, ...]
    t6_order: tuple[str, ...]
    t6_source_inputs: dict[str, FinalizedArtifactPin]
    source_sha256: dict[str, str]
    hidden_test_roster_sha256: str = Field(pattern=_HASH_PATTERN)
    output_root: str = "data/eval/m4"
    smoke_output_dir: str = "data/eval/m4/smoke"
    full_output_dir: str = "data/eval/m4/full"
    smoke_gate_required: Literal[True] = True

    @model_validator(mode="after")
    def _identity_is_governed(self) -> Config4RunFreeze:
        if tuple(self.systems) != tuple(CONFIG4_SYSTEMS):
            raise ValueError("configuration-4 system roster differs from the freeze")
        if not self.prompt_hashes:
            raise ValueError("configuration-4 prompt hashes are required")
        if (
            "adaptive_agent" in self.prompt_hashes
            and self.prompt_hashes["adaptive_agent"] != self.prompt_sha256
        ):
            raise ValueError("adaptive configuration-4 prompt hash differs")
        for name, value in {
            **self.prompt_hashes,
            **self.response_schema_hashes,
            **self.identity_hashes,
        }.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("configuration-4 identity hashes must be strings")
            if not re.fullmatch(_HASH_PATTERN, value):
                raise ValueError(f"configuration-4 identity hash is invalid: {name}")
        expected_identity_hashes = {
            "prompt": self.prompt_sha256,
            "response_schema": self.response_schema_sha256,
            "tool_policy": self.tool_policy_sha256,
            "verifier": self.verifier_sha256,
            "runner": self.runner_sha256,
            "predecessor_freeze": self.predecessor_freeze_sha256,
        }
        for name, expected in expected_identity_hashes.items():
            if self.identity_hashes.get(name) != expected:
                raise ValueError(f"configuration-4 identity hash is not pinned: {name}")
        expected_method_hash = canonical_sha256(
            _method_identity_payload(
                prompt_version=self.prompt_version,
                prompt_sha256=self.prompt_sha256,
                prompt_hashes=self.prompt_hashes,
                response_schema_sha256=self.response_schema_sha256,
                response_schema_hashes=self.response_schema_hashes,
                tool_policy_sha256=self.tool_policy_sha256,
                verifier_sha256=self.verifier_sha256,
                runner_sha256=self.runner_sha256,
            )
        )
        if self.method_identity_sha256 != expected_method_hash:
            raise ValueError("configuration-4 method identity hash differs")
        if self.hidden_test_roster_sha256 != canonical_sha256(
            {"test_order": list(self.test_order)}
        ):
            raise ValueError("configuration-4 held-out roster hash differs")
        output_root = self.output_root.replace("\\", "/").rstrip("/")
        smoke_dir = self.smoke_output_dir.replace("\\", "/").rstrip("/")
        full_dir = self.full_output_dir.replace("\\", "/").rstrip("/")
        if any(
            part.lower() == "m4-config3"
            for value in (output_root, smoke_dir, full_dir)
            for part in Path(value).parts
        ):
            raise ValueError(
                "configuration-4 artifact paths cannot use the configuration-3 tree"
            )
        if not _is_child(self.smoke_output_dir, self.output_root):
            raise ValueError("configuration-4 smoke output must be under its root")
        if not _is_child(self.full_output_dir, self.output_root):
            raise ValueError("configuration-4 full output must be under its root")
        if len(set(self.smoke_instance_ids)) != len(self.smoke_instance_ids):
            raise ValueError("configuration-4 smoke roster contains duplicates")
        if self.transport == "collaboration_subagent":
            if (
                self.provider != "collaboration_subagent"
                or self.authentication != "in_product_orchestration"
            ):
                raise ValueError("configuration-4 collaboration identity is inconsistent")
        else:
            if (
                self.provider != "chatgpt-codex"
                or self.authentication != "ChatGPT"
                or not self.chatgpt_account_sha256
                or not self.codex_cli_version
                or not self.wsl_distribution
                or not self.codex_binary
            ):
                raise ValueError("configuration-4 legacy identity is incomplete")
        return self


class Config4Predeclaration(BaseModel):
    """Provider-free receipt proving that configuration 4 was predeclared."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-predeclaration-v1"] = (
        "configuration-4-predeclaration-v1"
    )
    configuration: Literal[4] = 4
    status: Literal["PREDECLARED"] = "PREDECLARED"
    provider: Literal["collaboration_subagent", "chatgpt-codex"]
    authentication: Literal["in_product_orchestration", "ChatGPT"]
    model_id: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["max"] = "max"
    freeze_sha256: str = Field(pattern=_HASH_PATTERN)
    freeze_artifact_sha256: str = Field(pattern=_HASH_PATTERN)
    predecessor_freeze_sha256: str = Field(pattern=_HASH_PATTERN)
    prompt_version: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=_HASH_PATTERN)
    prompt_hashes: dict[str, str]
    response_schema_sha256: str = Field(pattern=_HASH_PATTERN)
    response_schema_hashes: dict[str, str]
    tool_policy_sha256: str = Field(pattern=_HASH_PATTERN)
    verifier_sha256: str = Field(pattern=_HASH_PATTERN)
    runner_sha256: str = Field(pattern=_HASH_PATTERN)
    method_identity_sha256: str = Field(pattern=_HASH_PATTERN)
    systems: tuple[Config4SystemID, ...]
    smoke_instance_ids: tuple[str, ...] = Field(min_length=14, max_length=14)
    test_order_sha256: str = Field(pattern=_HASH_PATTERN)
    output_root: str
    smoke_output_dir: str
    full_output_dir: str
    provider_calls_performed: Literal[0] = 0
    smoke_gate_required: Literal[True] = True


class Config4Progress(BaseModel):
    """Crash-safe successor progress consumed by the full-run gate."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["configuration-4-progress-v1"] = (
        "configuration-4-progress-v1"
    )
    configuration: Literal[4] = 4
    freeze_sha256: str = Field(pattern=_HASH_PATTERN)
    system_id: Config4SystemID
    run_mode: Config4RunMode
    completed_run_keys: list[str]
    pending_instance_ids: list[str]
    interruptions: dict[str, str]
    status: Literal["IN_PROGRESS", "VALID", "NOT_EVALUABLE"]


class Config4SmokeReadiness(BaseModel):
    """Hash-bound all-system smoke receipt required before full execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-smoke-readiness-v1"] = (
        "configuration-4-smoke-readiness-v1"
    )
    configuration: Literal[4] = 4
    freeze_sha256: str = Field(pattern=_HASH_PATTERN)
    systems: tuple[Config4SystemID, ...]
    progress_sha256: dict[str, str]
    status: Literal["VALID"] = "VALID"

    @model_validator(mode="after")
    def _all_systems_are_pinned(self) -> Config4SmokeReadiness:
        if tuple(self.systems) != tuple(CONFIG4_SYSTEMS):
            raise ValueError("configuration-4 smoke readiness system roster differs")
        if set(self.progress_sha256) != set(self.systems):
            raise ValueError("configuration-4 smoke readiness is missing a system")
        return self


def build_config4_freeze(
    *,
    predecessor: Config3RunFreeze,
    prompt: str | None = None,
    prompt_hashes: Mapping[str, str] | None = None,
    response_schema: Mapping[str, Any] | None = None,
    response_schema_hashes: Mapping[str, str] | None = None,
    tool_policy: str,
    verifier_identity: str,
    runner_identity: str,
    prompt_version: str = CONFIG4_PROMPT_VERSION,
    output_root: Path | str = CONFIG4_OUTPUT_DIR,
    systems: Sequence[Config4SystemID] = CONFIG4_SYSTEMS,
    budgets: Mapping[str, Mapping[str, Any]] | None = None,
    batch_sizes: Mapping[str, int] | None = None,
    max_workers: int | None = None,
    root: Path = ROOT,
) -> Config4RunFreeze:
    """Create a successor freeze without writing artifacts or calling a provider."""

    if predecessor.configuration != 3:
        raise ValueError("configuration-4 predecessor must be configuration 3")
    if not tool_policy or not verifier_identity or not runner_identity:
        raise ValueError("configuration-4 method identities must not be empty")
    if prompt_hashes is None:
        if prompt is None:
            raise ValueError("configuration-4 requires an exact prompt or prompt hashes")
        prompt_hashes = {"adaptive_agent": config4_prompt_sha256(prompt)}
    else:
        prompt_hashes = dict(prompt_hashes)
        if not prompt_hashes:
            raise ValueError("configuration-4 prompt hashes must not be empty")
        if prompt is not None:
            prompt_hash = config4_prompt_sha256(prompt)
            if prompt_hashes.get("adaptive_agent") not in {None, prompt_hash}:
                raise ValueError("configuration-4 prompt text/hash disagree")
            prompt_hashes.setdefault("adaptive_agent", prompt_hash)
    for name, value in prompt_hashes.items():
        if not name or not isinstance(value, str) or not re.fullmatch(
            _HASH_PATTERN, value
        ):
            raise ValueError(f"invalid configuration-4 prompt hash: {name}")
    prompt_sha256 = prompt_hashes.get("adaptive_agent") or canonical_sha256(
        dict(prompt_hashes)
    )
    if response_schema_hashes is None:
        if response_schema is None:
            raise ValueError(
                "configuration-4 requires an exact response schema or schema hashes"
            )
        response_schema_hashes = {
            "adaptive_agent": canonical_sha256(dict(response_schema))
        }
    else:
        response_schema_hashes = dict(response_schema_hashes)
        if not response_schema_hashes:
            raise ValueError("configuration-4 response schema hashes must not be empty")
    for name, value in response_schema_hashes.items():
        if not name or not isinstance(value, str) or not re.fullmatch(
            _HASH_PATTERN, value
        ):
            raise ValueError(f"invalid configuration-4 schema hash: {name}")
    response_schema_sha256 = response_schema_hashes.get("adaptive_agent") or canonical_sha256(
        dict(response_schema_hashes)
    )
    predecessor_hash = canonical_sha256(predecessor)
    tool_policy_sha256 = _sha_text(tool_policy)
    verifier_sha256 = _sha_text(verifier_identity)
    runner_sha256 = _sha_text(runner_identity)
    method_identity_sha256 = canonical_sha256(
        _method_identity_payload(
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            prompt_hashes=prompt_hashes,
            response_schema_sha256=response_schema_sha256,
            response_schema_hashes=response_schema_hashes,
            tool_policy_sha256=tool_policy_sha256,
            verifier_sha256=verifier_sha256,
            runner_sha256=runner_sha256,
        )
    )
    root = Path(root).resolve()
    output_text = _path_text(output_root, root=root)
    _guard_config4_output(output_text, root=root)
    smoke_text = (
        f"{output_text.rstrip('/')}/{CONFIG4_SMOKE_DIRECTORY}"
    )
    full_text = f"{output_text.rstrip('/')}/{CONFIG4_FULL_DIRECTORY}"
    payload = predecessor.model_dump(mode="json")
    payload.update(
        {
            "schema_version": "configuration-4-run-freeze-v1",
            "configuration": 4,
            "predecessor_configuration": 3,
            "predecessor_freeze_sha256": predecessor_hash,
            "prompt_version": prompt_version,
            "prompt_sha256": prompt_sha256,
            "prompt_hashes": dict(prompt_hashes),
            "response_schema_sha256": response_schema_sha256,
            "response_schema_hashes": dict(response_schema_hashes),
            "tool_policy_sha256": tool_policy_sha256,
            "verifier_sha256": verifier_sha256,
            "runner_sha256": runner_sha256,
            "method_identity_sha256": method_identity_sha256,
            "max_workers": (
                predecessor.max_workers if max_workers is None else max_workers
            ),
            "systems": tuple(systems),
            "budgets": {
                name: dict(value)
                for name, value in (
                    predecessor.budgets if budgets is None else budgets
                ).items()
            },
            "batch_sizes": dict(
                predecessor.batch_sizes if batch_sizes is None else batch_sizes
            ),
            "identity_hashes": {
                "prompt": prompt_sha256,
                "response_schema": response_schema_sha256,
                "tool_policy": tool_policy_sha256,
                "verifier": verifier_sha256,
                "runner": runner_sha256,
                "predecessor_freeze": predecessor_hash,
            },
            "hidden_test_roster_sha256": canonical_sha256(
                {"test_order": list(predecessor.test_order)}
            ),
            "output_root": output_text,
            "smoke_output_dir": smoke_text,
            "full_output_dir": full_text,
            "smoke_gate_required": True,
        }
    )
    return Config4RunFreeze.model_validate(payload)


def ensure_config4_frozen_identity(
    path: Path, freeze: Config4RunFreeze, *, root: Path = ROOT
) -> str:
    """Write one configuration-4 freeze once; never touch configuration 3."""

    path = _resolve_path(path, root=Path(root).resolve())
    _guard_config4_output(path, root=root)
    if path.exists():
        prior = Config4RunFreeze.model_validate_json(path.read_text(encoding="utf-8"))
        if prior != freeze:
            raise RuntimeError("configuration-4 run freeze differs from existing file")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, freeze.model_dump_json(indent=2))
    return canonical_sha256(freeze)


def load_config4_frozen_identity(path: Path) -> Config4RunFreeze:
    """Load only a configuration-4 freeze, rejecting historical schemas."""

    freeze = Config4RunFreeze.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if freeze.configuration != 4:
        raise ValueError("configuration-4 loader received a non-configuration-4 freeze")
    return freeze


def config4_run_key(
    *,
    freeze: Config4RunFreeze,
    system_id: Config4SystemID,
    run_mode: Config4RunMode,
    instance_id: str,
    source_sha256: str,
) -> str:
    """Bind a successor run key to configuration-4 identity and source."""

    if system_id not in freeze.systems:
        raise ValueError(f"{system_id!r} is not a frozen configuration-4 system")
    if not instance_id or not re.fullmatch(_HASH_PATTERN, source_sha256):
        raise ValueError("configuration-4 run key requires an instance and source hash")
    return canonical_sha256(
        {
            "configuration": 4,
            "freeze_sha256": canonical_sha256(freeze),
            "system_id": system_id,
            "run_mode": run_mode,
            "instance_id": instance_id,
            "source_sha256": source_sha256,
        }
    )


def _valid_config4_smoke_progress(
    *, output_dir: Path, freeze: Config4RunFreeze, system_id: Config4SystemID
) -> tuple[Config4Progress, str]:
    path = Path(output_dir) / CONFIG4_SMOKE_DIRECTORY / system_id / "progress.json"
    if not path.is_file():
        raise RuntimeError(f"{system_id} has no completed configuration-4 smoke")
    payload = path.read_bytes()
    progress = Config4Progress.model_validate_json(payload)
    if (
        progress.freeze_sha256 != canonical_sha256(freeze)
        or progress.system_id != system_id
        or progress.run_mode != "smoke"
        or progress.status != "VALID"
        or progress.pending_instance_ids
        or progress.interruptions
    ):
        raise RuntimeError(f"{system_id} configuration-4 smoke is not valid")
    expected_keys = {
        config4_run_key(
            freeze=freeze,
            system_id=system_id,
            run_mode="smoke",
            instance_id=instance_id,
            source_sha256=freeze.source_sha256[instance_id],
        )
        for instance_id in freeze.smoke_instance_ids
        if instance_id in freeze.source_sha256
    }
    if len(expected_keys) != len(freeze.smoke_instance_ids):
        raise RuntimeError("configuration-4 smoke roster has missing source hashes")
    if set(progress.completed_run_keys) != expected_keys:
        raise RuntimeError(f"{system_id} smoke does not contain the exact frozen run keys")
    return progress, hashlib.sha256(payload).hexdigest()


def refresh_config4_smoke_readiness(
    *, output_dir: Path, freeze: Config4RunFreeze
) -> Config4SmokeReadiness | None:
    """Write the immutable all-system successor smoke receipt when green."""

    _guard_config4_output(output_dir)
    hashes: dict[str, str] = {}
    for system_id in CONFIG4_SYSTEMS:
        try:
            _, hashes[system_id] = _valid_config4_smoke_progress(
                output_dir=Path(output_dir), freeze=freeze, system_id=system_id
            )
        except (OSError, RuntimeError, ValueError, KeyError):
            return None
    readiness = Config4SmokeReadiness(
        freeze_sha256=canonical_sha256(freeze),
        systems=CONFIG4_SYSTEMS,
        progress_sha256=hashes,
    )
    path = Path(output_dir) / "smoke-readiness.json"
    marker_path = path.with_suffix(".sha256")
    rendered = readiness.model_dump_json(indent=2)
    marker = hashlib.sha256(rendered.encode("utf-8")).hexdigest() + "\n"
    if path.exists() or marker_path.exists():
        if (
            not path.is_file()
            or not marker_path.is_file()
            or path.read_text(encoding="utf-8") != rendered
            or marker_path.read_text(encoding="utf-8") != marker
        ):
            raise RuntimeError("refusing to replace configuration-4 smoke readiness")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, rendered)
        _atomic_write(marker_path, marker)
    return readiness


def require_config4_full_smoke_readiness(
    *, output_dir: Path, freeze: Config4RunFreeze
) -> Config4SmokeReadiness:
    """Fail closed unless the exact all-system successor smoke has passed."""

    _guard_config4_output(output_dir)
    for system_id in CONFIG4_SYSTEMS:
        _valid_config4_smoke_progress(
            output_dir=Path(output_dir), freeze=freeze, system_id=system_id
        )
    path = Path(output_dir) / "smoke-readiness.json"
    marker_path = path.with_suffix(".sha256")
    if not path.is_file() or not marker_path.is_file():
        raise RuntimeError("configuration-4 full run requires the all-system smoke gate")
    rendered = path.read_text(encoding="utf-8")
    if marker_path.read_text(encoding="utf-8").strip() != hashlib.sha256(
        rendered.encode("utf-8")
    ).hexdigest():
        raise RuntimeError("configuration-4 smoke-readiness artifact hash mismatch")
    readiness = Config4SmokeReadiness.model_validate_json(rendered)
    current = refresh_config4_smoke_readiness(output_dir=output_dir, freeze=freeze)
    if current is None or readiness != current:
        raise RuntimeError("configuration-4 all-system smoke gate is stale")
    return readiness


def write_config4_predeclaration(
    *,
    freeze: Config4RunFreeze,
    output_dir: Path | str | None = None,
    root: Path = ROOT,
) -> Config4Predeclaration:
    """Persist the provider-free successor predeclaration immutably."""

    root = Path(root).resolve()
    target = (
        _resolve_path(output_dir, root=root)
        if output_dir is not None
        else _resolve_path(freeze.output_root, root=root)
    )
    _guard_config4_output(target, root=root)
    freeze_path = target / "run-freeze.json"
    ensure_config4_frozen_identity(freeze_path, freeze, root=root)
    predeclaration = Config4Predeclaration(
        provider=freeze.provider,
        authentication=freeze.authentication,
        freeze_sha256=canonical_sha256(freeze),
        freeze_artifact_sha256=_sha_file(freeze_path),
        predecessor_freeze_sha256=freeze.predecessor_freeze_sha256,
        prompt_version=freeze.prompt_version,
        prompt_sha256=freeze.prompt_sha256,
        prompt_hashes=freeze.prompt_hashes,
        response_schema_sha256=freeze.response_schema_sha256,
        response_schema_hashes=freeze.response_schema_hashes,
        tool_policy_sha256=freeze.tool_policy_sha256,
        verifier_sha256=freeze.verifier_sha256,
        runner_sha256=freeze.runner_sha256,
        method_identity_sha256=freeze.method_identity_sha256,
        systems=freeze.systems,
        smoke_instance_ids=freeze.smoke_instance_ids,
        test_order_sha256=freeze.hidden_test_roster_sha256,
        output_root=freeze.output_root,
        smoke_output_dir=freeze.smoke_output_dir,
        full_output_dir=freeze.full_output_dir,
    )
    path = target / "predeclaration.json"
    rendered = predeclaration.model_dump_json(indent=2)
    if path.exists():
        prior = Config4Predeclaration.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if prior != predeclaration:
            raise RuntimeError("configuration-4 predeclaration differs from existing file")
    else:
        _atomic_write(path, rendered)
    return predeclaration


def predeclare_config4(
    *,
    predecessor: Config3RunFreeze,
    prompt: str | None = None,
    prompt_hashes: Mapping[str, str] | None = None,
    response_schema: Mapping[str, Any] | None = None,
    response_schema_hashes: Mapping[str, str] | None = None,
    tool_policy: str,
    verifier_identity: str,
    runner_identity: str,
    prompt_version: str = CONFIG4_PROMPT_VERSION,
    output_root: Path | str = CONFIG4_OUTPUT_DIR,
    root: Path = ROOT,
) -> tuple[Config4RunFreeze, Config4Predeclaration]:
    """Build and persist the successor identity without provider execution."""

    freeze = build_config4_freeze(
        predecessor=predecessor,
        prompt=prompt,
        prompt_hashes=prompt_hashes,
        response_schema=response_schema,
        response_schema_hashes=response_schema_hashes,
        tool_policy=tool_policy,
        verifier_identity=verifier_identity,
        runner_identity=runner_identity,
        prompt_version=prompt_version,
        output_root=output_root,
        root=root,
    )
    return freeze, write_config4_predeclaration(
        freeze=freeze, output_dir=output_root, root=root
    )
