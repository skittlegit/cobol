"""Native transport gates for environments where WSL is unavailable."""

from __future__ import annotations

import json
from pathlib import Path

from cobol_archaeologist.eval.codex_batch import sanitized_codex_environment
from cobol_archaeologist.eval.codex_live import codex_request_sha256
from cobol_archaeologist.eval.codex_native import (
    native_chatgpt_account_sha256,
    native_codex_exec_arguments,
    native_tool_command,
    stage_native_task,
)
from cobol_archaeologist.eval.materialize import MaterializedSource


def test_native_arguments_preserve_ephemeral_luna_max_identity(tmp_path: Path):
    arguments = native_codex_exec_arguments(
        codex_binary="codex.exe",
        task_root=tmp_path,
        model_id="gpt-5.6-luna",
        reasoning_effort="max",
    )

    assert arguments[0] == "codex.exe"
    assert "--ephemeral" in arguments
    assert "--ignore-user-config" in arguments
    assert "--ignore-rules" in arguments
    assert arguments[arguments.index("-m") + 1] == "gpt-5.6-luna"
    assert 'model_reasoning_effort="max"' in arguments
    assert not any(argument == "env" for argument in arguments)
    baseline = native_codex_exec_arguments(
        codex_binary="codex.exe",
        task_root=tmp_path,
        model_id="gpt-5.6-luna",
        reasoning_effort="max",
        allow_tool_bridge=False,
    )
    assert baseline[baseline.index("--sandbox") + 1] == "read-only"


def test_native_account_freeze_is_account_specific_and_never_token_derived(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    auth = codex_home / "auth.json"
    environment = {"CODEX_HOME": str(codex_home)}
    auth.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"account_id": "account-one", "access_token": "secret-a"},
            }
        ),
        encoding="utf-8",
    )
    first = native_chatgpt_account_sha256(environment)
    auth.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"account_id": "account-two", "access_token": "secret-a"},
            }
        ),
        encoding="utf-8",
    )
    second = native_chatgpt_account_sha256(environment)
    assert first != second
    assert "secret-a" not in first + second


def test_request_identity_normalizes_random_native_task_roots(tmp_path: Path) -> None:
    source = MaterializedSource(
        main_file="PROGRAM.cbl",
        files={"PROGRAM.cbl": "IDENTIFICATION DIVISION.\n"},
        source_sha256="0" * 64,
    )

    def request(root: Path) -> str:
        return codex_request_sha256(
            prompt="review one case",
            schema={"type": "object"},
            sources={"drift_900000": source},
            model_id="gpt-5.6-luna",
            reasoning_effort="max",
            cli_arguments=native_codex_exec_arguments(
                codex_binary="codex.exe",
                task_root=root,
                model_id="gpt-5.6-luna",
                reasoning_effort="max",
            ),
            runtime_source_sha256="1" * 64,
            transport="native",
            authentication_identity_sha256="2" * 64,
            authorized_hunts=("adaptive",),
            task_root=str(root),
        )

    assert request(tmp_path / "random-a") == request(tmp_path / "random-b")


def test_native_staging_contains_only_opaque_descriptor_and_source(tmp_path: Path):
    source = MaterializedSource(
        main_file="PROGRAM.cbl",
        files={"PROGRAM.cbl": "IDENTIFICATION DIVISION.\n"},
        source_sha256="0" * 64,
    )
    root = stage_native_task(
        prompt="one opaque case",
        schema={"type": "object"},
        sources={"drift_900000": source},
        task_base=tmp_path,
    )

    assert (root / "cases/drift_900000/PROGRAM.cbl").is_file()
    descriptor = (root / "descriptor.json").read_text(encoding="utf-8")
    assert "drift_900000" in descriptor
    assert "instance_id" not in descriptor
    assert "provenance" not in descriptor
    command = native_tool_command()
    assert "cobol_archaeologist.eval.codex_tool" in command
    assert ".venv" in command
    assert "python.exe" in command


def test_native_environment_strips_all_api_key_routes():
    clean = sanitized_codex_environment(
        {
            "PATH": "x",
            "OPENAI_API_KEY": "secret",
            "CODEX_API_KEY": "secret",
            "AZURE_OPENAI_API_KEY": "secret",
            "ANTHROPIC_API_KEY": "secret",
            "FUTURE_PROVIDER_TOKEN": "secret",
        }
    )
    assert clean == {"PATH": "x"}
