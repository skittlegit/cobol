"""Prepare the pinned 40-side adaptive temporal add-on without provider calls.

Only coordinator task metadata is extended to temporal mode. Frozen method,
prompt builders, schemas, tools, and verifier remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from cobol_archaeologist.eval.codex_tool import ADAPTIVE_HUNT
from cobol_archaeologist.eval.collaboration_staging import stage_collaboration_task
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationGroupIdentity,
    build_collaboration_request,
    ensure_collaboration_request,
)
from cobol_archaeologist.eval.config3_live import (
    load_finalized_t6_rows,
    materialize_finalized_t6_row,
    runtime_source_sha256,
)
from cobol_archaeologist.eval.config4_live import (
    canonical_sha256,
    config4_run_key,
    load_config4_frozen_identity,
    require_config4_full_smoke_readiness,
)
from cobol_archaeologist.eval.config4_runner import (
    Config4PreparedTask,
    Config4RunPreparation,
    _build_prompt_parts,
)


class TemporalPreparedTask(Config4PreparedTask):
    schema_version: Literal["configuration-4-temporal-prepared-task-v1"] = (
        "configuration-4-temporal-prepared-task-v1"
    )
    run_mode: Literal["temporal"] = "temporal"


class TemporalPreparation(Config4RunPreparation):
    schema_version: Literal["configuration-4-temporal-preparation-v1"] = (
        "configuration-4-temporal-preparation-v1"
    )
    run_mode: Literal["temporal"] = "temporal"
    tasks: tuple[TemporalPreparedTask, ...]


def write_immutable(path: Path, value: dict) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"refusing to replace immutable {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    freeze = load_config4_frozen_identity(output / "run-freeze.json")
    require_config4_full_smoke_readiness(output_dir=output, freeze=freeze)
    if runtime_source_sha256(root) != freeze.runtime_source_sha256:
        raise RuntimeError("frozen method runtime changed")
    manifest_path = root / freeze.t6_v2_path
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != freeze.t6_v2_sha256:
        raise RuntimeError("frozen temporal manifest changed")
    manifest, rows = load_finalized_t6_rows(root=root, manifest_path=manifest_path)
    if (
        tuple(row.instance_id for row in rows) != freeze.t6_order
        or manifest.source_inputs != freeze.t6_source_inputs
        or len(rows) != 40
        or len(manifest.pair_order) != 20
    ):
        raise RuntimeError("temporal roster differs from the frozen 20-pair add-on")
    tasks = []
    artifact_dir = output / "temporal/adaptive_agent"
    staging_base = artifact_dir / "task-staging"
    for ordinal, row in enumerate(rows, start=1):
        source = materialize_finalized_t6_row(
            row, root=root, source_inputs=freeze.t6_source_inputs
        )
        if source.source_sha256 != freeze.source_sha256[row.instance_id]:
            raise RuntimeError("temporal source differs from frozen identity")
        key = config4_run_key(
            freeze=freeze,
            system_id="adaptive_agent",
            run_mode="temporal",
            instance_id=row.instance_id,
            source_sha256=source.source_sha256,
        )
        staged = stage_collaboration_task(
            staging_base=staging_base,
            run_key=key,
            sources={"drift_900000": source},
            authorized_hunts=(ADAPTIVE_HUNT,),
        )
        prompt, schema, sources = _build_prompt_parts(
            system_id="adaptive_agent",
            batch=[row],
            sources={row.instance_id: source},
            contexts={},
            tool_command=staged.tool_command,
        )
        if canonical_sha256(schema) != freeze.response_schema_hashes["adaptive_agent"]:
            raise RuntimeError("temporal response schema differs from frozen method")
        request = build_collaboration_request(
            model_id=freeze.model_id,
            run_key=key,
            prompt=prompt,
            schema=schema,
            sources=sources,
            runtime_source_sha256=freeze.runtime_source_sha256,
            authorized_hunts=(ADAPTIVE_HUNT,),
            visible_cases=1,
            group=CollaborationGroupIdentity(
                group_id="config4:temporal:adaptive_agent",
                mode="concurrent",
                ordinal=ordinal,
                size=len(rows),
            ),
        )
        request_path = artifact_dir / "requests" / f"{key}.json"
        ensure_collaboration_request(request_path, request)
        tasks.append(
            TemporalPreparedTask(
                freeze_sha256=canonical_sha256(freeze),
                system_id="adaptive_agent",
                ordinal=ordinal,
                task_key=key,
                row_instance_ids=(row.instance_id,),
                row_run_keys=(key,),
                request_path=request_path,
                artifact_dir=artifact_dir,
                staging_base=staging_base,
                staging_sha256=staged.staging_sha256,
                tool_command=staged.tool_command,
                request_sha256=request.request_sha256,
                prompt_sha256=request.prompt_sha256,
                schema_sha256=request.schema_sha256,
                visible_cases=1,
            )
        )
    preparation = TemporalPreparation(
        freeze_sha256=canonical_sha256(freeze),
        systems=("adaptive_agent",),
        row_order=tuple(row.instance_id for row in rows),
        task_count=len(tasks),
        tasks=tuple(tasks),
    )
    write_immutable(output / "temporal/run-preparation.json", preparation.model_dump(mode="json"))
    receipt = {
        "schema_version": "configuration-4-temporal-preparation-receipt-v1",
        "configuration": 4,
        "freeze_sha256": canonical_sha256(freeze),
        "method_identity_sha256": freeze.method_identity_sha256,
        "runtime_source_sha256": freeze.runtime_source_sha256,
        "finalized_t6_sha256": freeze.t6_v2_sha256,
        "preparation_sha256": canonical_sha256(preparation),
        "model_id": freeze.model_id,
        "reasoning_effort": freeze.reasoning_effort,
        "pair_count": 20,
        "side_count": 40,
        "system_id": "adaptive_agent",
        "task_count": 40,
        "provider_calls_performed": 0,
        "method_changes": False,
        "execution_gate": "Complete the 610-task full-run handoff before temporal execution",
        "coordinator_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    write_immutable(output / "temporal/preparation-receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
