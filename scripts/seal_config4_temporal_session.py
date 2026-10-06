"""Capture an exact isolated temporal final after terminal full-run coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from prepare_config4_temporal import TemporalPreparation

from cobol_archaeologist.eval.config3_live import runtime_source_sha256
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
    parser.add_argument("--ordinal", type=int, required=True)
    parser.add_argument("--session", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    root = Path(__file__).resolve().parents[1]
    freeze = load_config4_frozen_identity(output / "run-freeze.json")
    identity = json.loads((output / "full-run-identity.json").read_text())
    handoff = json.loads((output / "full/r1.5-handoff.json").read_text())
    full = Config4RunPreparation.model_validate_json(
        (output / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    if (
        full.task_count != 610
        or canonical_sha256(identity) != handoff["full_run_identity_sha256"]
        or canonical_sha256(full) != identity["preparation_sha256"]
        or full.freeze_sha256 != canonical_sha256(freeze)
        or runtime_source_sha256(root) != freeze.runtime_source_sha256
    ):
        raise RuntimeError("full-run or runtime identity differs from freeze")
    for task in full.tasks:
        if not (task.artifact_dir / "raw" / task.task_key / "complete").is_file():
            raise RuntimeError("temporal execution requires terminal full-run coverage")
        replay_config4_capture(task=task)
    preparation = TemporalPreparation.model_validate_json(
        (output / "temporal/run-preparation.json").read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (output / "temporal/preparation-receipt.json").read_text(encoding="utf-8")
    )
    if (
        preparation.freeze_sha256 != canonical_sha256(freeze)
        or canonical_sha256(preparation) != receipt["preparation_sha256"]
        or preparation.row_order != freeze.t6_order
        or preparation.task_count != 40
    ):
        raise RuntimeError("temporal preparation differs from pinned identity")
    task = next(task for task in preparation.tasks if task.ordinal == args.ordinal)
    rows = [
        json.loads(line)
        for line in args.session.read_text(encoding="utf-8").splitlines()
    ]
    contexts = [row["payload"] for row in rows if row["type"] == "turn_context"]
    if not contexts or any(
        context["model"] != freeze.model_id
        or context["effort"] != freeze.reasoning_effort
        for context in contexts
    ):
        raise RuntimeError("temporal evaluator model or reasoning differs")
    name = rows[0]["payload"]["source"]["subagent"]["thread_spawn"]["agent_path"]
    if name != f"/root/r16_temporal_{args.ordinal:03d}":
        raise RuntimeError("temporal session belongs to another isolated side")
    final = next(
        (
            row["payload"]["content"][0]["text"]
            for row in reversed(rows)
            if row.get("payload", {}).get("phase") == "final_answer"
        ),
        None,
    )
    if final is None:
        raise RuntimeError("session has no final; leave task unsealed")
    digest = hashlib.sha256(final.encode("utf-8")).hexdigest()
    try:
        envelope = _response_model("adaptive_agent").model_validate_json(final)
        if [result.alias for result in envelope.results] != ["drift_900000"]:
            raise ValueError("temporal final has an unexpected alias")
    except ValueError:
        diagnostic = (
            output / "temporal/rejected-finals" / f"{args.ordinal:03d}-{digest}.json"
        )
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        if not diagnostic.exists():
            diagnostic.write_text(final, encoding="utf-8", newline="\n")
        raise
    capture = (
        output / "temporal/captured-finals" / f"adaptive_agent-{args.ordinal:03d}.json"
    )
    capture.parent.mkdir(parents=True, exist_ok=True)
    if capture.exists():
        if capture.read_text(encoding="utf-8") != final:
            raise RuntimeError("refusing to replace exact temporal final")
    else:
        capture.write_text(final, encoding="utf-8", newline="\n")
    seal_config4_capture(task=task, final_json=final, task_name=name, task_id=name)
    replay_config4_capture(task=task)
    print(
        json.dumps(
            {
                "ordinal": args.ordinal,
                "task_key": task.task_key,
                "final_sha256": digest,
                "status": "SEALED_AND_REPLAYED",
            }
        )
    )


if __name__ == "__main__":
    main()
