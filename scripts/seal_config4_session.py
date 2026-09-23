"""Seal one exact Codex collaboration final against a prepared configuration-4 task."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from cobol_archaeologist.eval.config4_live import (
    canonical_sha256,
    load_config4_frozen_identity,
)
from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    _response_model,
    replay_config4_capture,
    seal_config4_capture,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--system", required=True)
    parser.add_argument("--ordinal", type=int, required=True)
    parser.add_argument("--session", type=Path, required=True)
    args = parser.parse_args()

    freeze = load_config4_frozen_identity(args.output / "run-freeze.json")
    preparation = Config4RunPreparation.model_validate_json(
        (args.output / args.mode / "run-preparation.json").read_text(encoding="utf-8")
    )
    if preparation.freeze_sha256 != canonical_sha256(freeze):
        raise RuntimeError("preparation differs from frozen run")
    task = next(
        task
        for task in preparation.tasks
        if task.system_id == args.system and task.ordinal == args.ordinal
    )
    with args.session.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    metadata = rows[0]["payload"]
    name = metadata["source"]["subagent"]["thread_spawn"]["agent_path"]
    context = next(row["payload"] for row in rows if row["type"] == "turn_context")
    if context["model"] != freeze.model_id or context["effort"] != freeze.reasoning_effort:
        raise RuntimeError("subagent model or reasoning differs from frozen run")
    final = next(
        row["payload"]["content"][0]["text"]
        for row in reversed(rows)
        if row["payload"].get("phase") == "final_answer"
    )
    try:
        _response_model(args.system).model_validate_json(final)
    except ValidationError:
        diagnostic = (
            args.output
            / "rejected-finals"
            / f"{args.system}-{args.ordinal:03d}-{hashlib.sha256(final.encode('utf-8')).hexdigest()}.json"
        )
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        if not diagnostic.exists():
            diagnostic.write_text(final, encoding="utf-8", newline="\n")
        raise
    capture = (
        args.output
        / f"{args.mode}-captured-finals"
        / f"{args.system}-{args.ordinal:03d}.json"
    )
    capture.parent.mkdir(parents=True, exist_ok=True)
    if capture.exists():
        if capture.read_text(encoding="utf-8") != final:
            raise RuntimeError("refusing to replace exact captured final")
    else:
        capture.write_text(final, encoding="utf-8", newline="\n")
    seal_config4_capture(task=task, final_json=final, task_name=name, task_id=name)
    replay_config4_capture(task=task)
    print(
        json.dumps(
            {
                "system": args.system,
                "ordinal": args.ordinal,
                "task_key": task.task_key,
                "model_id": freeze.model_id,
                "final_sha256": hashlib.sha256(final.encode("utf-8")).hexdigest(),
                "status": "SEALED_AND_REPLAYED",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
