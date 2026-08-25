"""Provider-free identity and smoke gates for configuration 4."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.eval.config3_live import Config3RunFreeze
from cobol_archaeologist.eval.config4_live import (
    CONFIG4_SYSTEMS,
    Config4Progress,
    Config4RunFreeze,
    build_config4_freeze,
    canonical_sha256,
    config4_prompt_sha256,
    config4_run_key,
    ensure_config4_frozen_identity,
    predeclare_config4,
    refresh_config4_smoke_readiness,
    require_config4_full_smoke_readiness,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG3_FREEZE_PATH = (
    ROOT / "data/eval/m4-config3/lineage-v4/run-freeze-v2.json"
)


def _predecessor() -> Config3RunFreeze:
    return Config3RunFreeze.model_validate_json(
        CONFIG3_FREEZE_PATH.read_text(encoding="utf-8")
    )


def _freeze(tmp_path: Path):
    prompt = "You are the configuration-4 adaptive successor."
    return build_config4_freeze(
        predecessor=_predecessor(),
        prompt=prompt,
        response_schema={
            "type": "object",
            "properties": {"results": {"type": "array"}},
            "required": ["results"],
            "additionalProperties": False,
        },
        tool_policy="one bounded command, at most sixteen calls",
        verifier_identity="unchanged-config3-verifier-v1",
        runner_identity="config4-runner-v1",
        output_root=tmp_path / "m4-config4",
    )


def test_historical_configuration3_freeze_remains_loadable_and_unchanged():
    before = hashlib.sha256(CONFIG3_FREEZE_PATH.read_bytes()).hexdigest()
    freeze = _predecessor()
    after = hashlib.sha256(CONFIG3_FREEZE_PATH.read_bytes()).hexdigest()

    assert freeze.configuration == 3
    assert before == after


def test_configuration4_pins_predecessor_and_method_affecting_hashes(tmp_path: Path):
    freeze = _freeze(tmp_path)

    assert isinstance(freeze, Config4RunFreeze)
    assert freeze.configuration == 4
    assert freeze.predecessor_configuration == 3
    assert freeze.predecessor_freeze_sha256 == canonical_sha256(_predecessor())
    assert freeze.prompt_sha256 == config4_prompt_sha256(
        "You are the configuration-4 adaptive successor."
    )
    assert freeze.identity_hashes["prompt"] == freeze.prompt_sha256
    assert freeze.identity_hashes["response_schema"] == freeze.response_schema_sha256
    assert freeze.smoke_gate_required is True
    assert "m4-config3" not in freeze.output_root

    changed = freeze.model_dump(mode="json")
    changed["prompt_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="prompt hash differs"):
        Config4RunFreeze.model_validate(changed)


def test_configuration4_writer_refuses_configuration3_tree_without_mutation(
    tmp_path: Path,
):
    freeze = _freeze(tmp_path)
    before = hashlib.sha256(CONFIG3_FREEZE_PATH.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="cannot be written under"):
        ensure_config4_frozen_identity(CONFIG3_FREEZE_PATH, freeze)

    assert hashlib.sha256(CONFIG3_FREEZE_PATH.read_bytes()).hexdigest() == before


def test_predeclaration_is_additive_and_provider_free(tmp_path: Path):
    predecessor = _predecessor()
    freeze, predeclaration = predeclare_config4(
        predecessor=predecessor,
        prompt="A predeclared configuration-4 prompt.",
        response_schema={"type": "object", "additionalProperties": False},
        tool_policy="bounded",
        verifier_identity="verifier-v1",
        runner_identity="runner-v1",
        output_root=tmp_path / "m4-config4",
    )
    output = tmp_path / "m4-config4"

    assert freeze.configuration == 4
    assert predeclaration.configuration == 4
    assert predeclaration.provider_calls_performed == 0
    assert (output / "run-freeze.json").is_file()
    assert (output / "predeclaration.json").is_file()
    assert not (tmp_path / "m4-config3" / "run-freeze.json").exists()


def test_configuration4_full_execution_is_smoke_gated(tmp_path: Path):
    freeze = _freeze(tmp_path)
    output = tmp_path / "m4-config4"

    with pytest.raises(RuntimeError, match="no completed configuration-4 smoke"):
        require_config4_full_smoke_readiness(output_dir=output, freeze=freeze)

    for system_id in CONFIG4_SYSTEMS:
        keys = [
            config4_run_key(
                freeze=freeze,
                system_id=system_id,
                run_mode="smoke",
                instance_id=instance_id,
                source_sha256=freeze.source_sha256[instance_id],
            )
            for instance_id in freeze.smoke_instance_ids
        ]
        path = output / "smoke" / system_id / "progress.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            Config4Progress(
                freeze_sha256=canonical_sha256(freeze),
                system_id=system_id,
                run_mode="smoke",
                completed_run_keys=keys,
                pending_instance_ids=[],
                interruptions={},
                status="VALID",
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )

    readiness = refresh_config4_smoke_readiness(
        output_dir=output, freeze=freeze
    )
    assert readiness is not None
    assert require_config4_full_smoke_readiness(
        output_dir=output, freeze=freeze
    ) == readiness

    bad = output / "smoke" / "agent" / "progress.json"
    payload = Config4Progress.model_validate_json(bad.read_text(encoding="utf-8"))
    bad.write_text(
        payload.model_copy(update={"status": "IN_PROGRESS"}).model_dump_json(
            indent=2
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="smoke is not valid"):
        require_config4_full_smoke_readiness(output_dir=output, freeze=freeze)
