"""Replay and score the complete frozen temporal add-on without provider calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from prepare_config4_temporal import TemporalPreparation, write_immutable

from cobol_archaeologist.eval.config3_live import (
    Config3TemporalScore,
    TemporalPairScore,
    _replay_adaptive_record,
    _write_record_sidecar,
    load_finalized_t6_rows,
    materialize_finalized_t6_row,
    runtime_source_sha256,
)
from cobol_archaeologist.eval.config4_live import (
    canonical_sha256,
    config4_run_key,
    load_config4_frozen_identity,
)
from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    replay_config4_capture,
)
from cobol_archaeologist.eval.metrics import versioned_judgment
from cobol_archaeologist.model.verify import default_entailer


class Config4TemporalScore(Config3TemporalScore):
    schema_version: Literal["configuration-4-temporal-score-v1"] = (
        "configuration-4-temporal-score-v1"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    freeze = load_config4_frozen_identity(output / "run-freeze.json")
    full = Config4RunPreparation.model_validate_json(
        (output / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    identity = json.loads((output / "full-run-identity.json").read_text())
    handoff = json.loads((output / "full/r1.5-handoff.json").read_text())
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
            raise RuntimeError("temporal scoring requires terminal full-run coverage")
        replay_config4_capture(task=task)
    preparation = TemporalPreparation.model_validate_json(
        (output / "temporal/run-preparation.json").read_text(encoding="utf-8")
    )
    receipt = json.loads((output / "temporal/preparation-receipt.json").read_text())
    if (
        canonical_sha256(preparation) != receipt["preparation_sha256"]
        or preparation.freeze_sha256 != canonical_sha256(freeze)
        or preparation.row_order != freeze.t6_order
        or preparation.task_count != 40
        or preparation.systems != ("adaptive_agent",)
    ):
        raise RuntimeError("temporal preparation differs from pinned identity")
    # Check complete coverage before loading gold or initializing the verifier.
    for task in preparation.tasks:
        if not (task.artifact_dir / "raw" / task.task_key / "complete").is_file():
            raise RuntimeError("temporal scoring requires all 40 sealed sides")
    manifest_path = root / freeze.t6_v2_path
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != freeze.t6_v2_sha256:
        raise RuntimeError("temporal manifest changed")
    manifest, rows = load_finalized_t6_rows(root=root, manifest_path=manifest_path)
    if manifest.instance_order != preparation.row_order:
        raise RuntimeError("temporal side order changed")
    entailer = default_entailer()
    records = []
    execution_hashes = {}
    artifact_dir = output / "temporal/adaptive_agent"
    for row, task in zip(rows, preparation.tasks, strict=True):
        source = materialize_finalized_t6_row(
            row, root=root, source_inputs=freeze.t6_source_inputs
        )
        key = config4_run_key(
            freeze=freeze,
            system_id="adaptive_agent",
            run_mode="temporal",
            instance_id=row.instance_id,
            source_sha256=source.source_sha256,
        )
        if (
            source.source_sha256 != freeze.source_sha256[row.instance_id]
            or task.task_key != key
            or task.row_instance_ids != (row.instance_id,)
            or task.row_run_keys != (key,)
        ):
            raise RuntimeError("temporal source or run key changed")
        execution = replay_config4_capture(task=task)
        record = _replay_adaptive_record(
            row, source=source, execution=execution, key=key, entailer=entailer
        )
        _write_record_sidecar(
            artifact_dir / "records" / f"{key}.json",
            record,
            execution=execution,
            raw_bundle_key=task.task_key,
        )
        records.append(record)
        execution_hashes[key] = canonical_sha256(execution)
    by_id = {record.instance_id: record for record in records}

    def correct(instance_id: str) -> bool:
        record = by_id[instance_id]
        return bool(
            not record.infrastructure_error
            and not record.abstained
            and record.prediction is not None
            and (record.prediction.drift_type != "D7_conformant")
            == (record.gold.drift_type != "D7_conformant")
        )

    pairs = tuple(
        TemporalPairScore(
            pair_id=pair_id,
            instance_ids=manifest.pair_members[pair_id],
            authority_target=manifest.authority_targets[pair_id],
            side_correct=tuple(
                correct(item) for item in manifest.pair_members[pair_id]
            ),
            pair_correct=all(correct(item) for item in manifest.pair_members[pair_id]),
        )
        for pair_id in manifest.pair_order
    )
    records_value = [record.model_dump(mode="json") for record in records]
    records_path = artifact_dir / "replayed-records.json"
    write_immutable(records_path, {"records": records_value})
    score = Config4TemporalScore(
        freeze_sha256=canonical_sha256(freeze),
        finalized_t6_sha256=freeze.t6_v2_sha256,
        records_sha256=hashlib.sha256(records_path.read_bytes()).hexdigest(),
        pair_order=manifest.pair_order,
        pairs=pairs,
        paired_correct=sum(pair.pair_correct for pair in pairs),
        paired_accuracy=sum(pair.pair_correct for pair in pairs) / 20,
    )
    validity = {
        "infrastructure_errors": sum(bool(r.infrastructure_error) for r in records),
        "unverified_emissions": sum(
            r.prediction is not None
            and (r.verification is None or not r.verification.verified)
            for r in records
        ),
        "contract_repairs": sum(
            r.trajectory.contract_repairs for r in records if r.trajectory is not None
        ),
    }
    paired_metrics = versioned_judgment(records)
    if (
        paired_metrics["pairs"] != 20
        or paired_metrics["successes"] != score.paired_correct
        or paired_metrics["paired_accuracy"] != score.paired_accuracy
    ):
        raise RuntimeError("manifest pairing and frozen temporal metric disagree")
    write_immutable(
        artifact_dir / "replay-audit.json",
        {
            "schema_version": "configuration-4-temporal-replay-audit-v1",
            "preparation_sha256": canonical_sha256(preparation),
            "execution_sha256": execution_hashes,
            "rows_replayed": len(records),
            "validity": validity,
            "paired_metrics": paired_metrics,
            "provider_calls_performed": 0,
            "provider_resource_telemetry": "not_recorded",
            "status": "VALID" if not any(validity.values()) else "MEASURED_FAILURES",
        },
    )
    # Never issue a valid gate for infrastructure or contract failures.
    if any(validity.values()):
        raise RuntimeError(
            "temporal measured failures preserved; no VALID score issued"
        )
    score_path = artifact_dir / "paired-score.json"
    write_immutable(score_path, score.model_dump(mode="json"))
    digest = hashlib.sha256(score_path.read_bytes()).hexdigest()
    marker = score_path.with_suffix(".sha256")
    if marker.exists() and marker.read_text(encoding="utf-8") != digest + "\n":
        raise RuntimeError("temporal score hash marker differs")
    if not marker.exists():
        marker.write_text(digest + "\n", encoding="utf-8", newline="\n")
    write_immutable(
        artifact_dir / "score-receipt.json",
        {
            "schema_version": "configuration-4-temporal-score-receipt-v1",
            "freeze_sha256": canonical_sha256(freeze),
            "preparation_sha256": canonical_sha256(preparation),
            "paired_score_sha256": digest,
            "replay_audit_sha256": hashlib.sha256(
                (artifact_dir / "replay-audit.json").read_bytes()
            ).hexdigest(),
            "records_sha256": score.records_sha256,
            "status": "VALID",
        },
    )
    print(json.dumps({"status": "VALID", "pairs": 20, "sides": 40}))


if __name__ == "__main__":
    main()
