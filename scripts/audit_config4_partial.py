"""Read-only host replay audit of sealed configuration-4 tasks.

Prints task-level validity counts without exposing held-out labels or predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.eval.config3_controls import (
    RAG_RETRIEVAL_MODES,
    build_control_contexts,
    replay_agent_batch,
    replay_baseline_batch,
)
from cobol_archaeologist.eval.config3_live import _load_split, _replay_adaptive_record
from cobol_archaeologist.eval.config4_live import load_config4_frozen_identity
from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    replay_config4_capture,
)
from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.model.verify import default_entailer
from cobol_archaeologist.rag.search import RegulationSearch

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--system",
        choices=(
            "agent",
            "adaptive_agent",
            "plain_llm",
            "rag_dense",
            "rag_reranker",
            "oracle_slice",
        ),
    )
    parser.add_argument("--ordinal", type=int)
    args = parser.parse_args()

    output = args.output.resolve()
    freeze = load_config4_frozen_identity(output / "run-freeze.json")
    preparation = Config4RunPreparation.model_validate_json(
        (output / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    test_path = ROOT / freeze.test_split_path
    if hashlib.sha256(test_path.read_bytes()).hexdigest() != freeze.test_split_sha256:
        raise RuntimeError("hidden split differs from frozen hash")
    rows = _load_split(test_path)
    if tuple(row.instance_id for row in rows) != freeze.test_order:
        raise RuntimeError("hidden row order differs from freeze")
    by_id = {row.instance_id: row for row in rows}
    entailer = default_entailer()
    searches = {
        system_id: RegulationSearch(mode=mode)
        for system_id, mode in RAG_RETRIEVAL_MODES.items()
        if args.system is None or args.system == system_id
    }
    reports = []
    for task in preparation.tasks:
        if args.system and task.system_id != args.system:
            continue
        if args.ordinal is not None and task.ordinal != args.ordinal:
            continue
        if not (task.artifact_dir / "raw" / task.task_key / "complete").is_file():
            continue
        execution = replay_config4_capture(task=task)
        batch = [by_id[instance_id] for instance_id in task.row_instance_ids]
        sources = {row.instance_id: materialize(row) for row in batch}
        row_keys = dict(zip(task.row_instance_ids, task.row_run_keys, strict=True))
        if task.system_id == "agent":
            records = replay_agent_batch(
                batch=batch,
                execution=execution,
                sources=sources,
                row_keys=row_keys,
                entailer=entailer,
            )
        else:
            if task.system_id == "adaptive_agent":
                row = batch[0]
                records = [
                    _replay_adaptive_record(
                        row,
                        source=sources[row.instance_id],
                        execution=execution,
                        key=row_keys[row.instance_id],
                        entailer=entailer,
                    )
                ]
            else:
                contexts = build_control_contexts(
                    task.system_id,
                    rows=batch,
                    sources=sources,
                    regulation_search=searches.get(task.system_id),
                )
                records = replay_baseline_batch(
                    system_id=task.system_id,
                    batch=batch,
                    execution=execution,
                    sources=sources,
                    contexts=contexts,
                    row_keys=row_keys,
                    entailer=entailer,
                )
        reports.append(
            {
                "system_id": task.system_id,
                "ordinal": task.ordinal,
                "task_key": task.task_key,
                "rows": len(records),
                "infrastructure_errors": sum(
                    record.infrastructure_error is not None for record in records
                ),
                "predictions": sum(record.prediction is not None for record in records),
                "unverified_emissions": sum(
                    record.prediction is not None
                    and (record.verification is None or not record.verification.verified)
                    for record in records
                ),
                "contract_repairs": sum(
                    record.trajectory.contract_repairs
                    for record in records
                    if record.trajectory is not None
                ),
            }
        )
    print(json.dumps({"tasks_audited": len(reports), "tasks": reports}, indent=2))


if __name__ == "__main__":
    main()
