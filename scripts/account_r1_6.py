"""Summarize sealed R1.6 observation and telemetry metadata without scoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from collect_r1_6_sessions import write_json

from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    replay_config4_capture,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    prep = Config4RunPreparation.model_validate_json(
        (output / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    by_ordinal = {(task.system_id, task.ordinal): task for task in prep.tasks}
    ledger = json.loads((output / "full/r1.6-captures.json").read_text())
    reports = []
    seen = set()
    for capture in ledger["captures"]:
        task = by_ordinal[(capture["system_id"], capture["ordinal"])]
        if task.task_key in seen:
            raise RuntimeError("duplicate R1.6 capture")
        seen.add(task.task_key)
        execution = replay_config4_capture(task=task)
        reports.append(
            {
                "system_id": task.system_id,
                "ordinal": task.ordinal,
                "task_key": task.task_key,
                "signed_observations": len(execution.tool_logs),
                "signed_observation_errors": sum(
                    log.error is not None for log in execution.tool_logs
                ),
                "truncated_observations": sum(
                    log.observation_truncated for log in execution.tool_logs
                ),
                "provider_usage_status": execution.usage_evidence.status,
                "provider_timing_status": execution.timing_evidence.status,
                "resource_evidence_valid": execution.resource_evidence_valid,
                "evidence_scope": execution.evidence_scope,
            }
        )
    report = {
        "schema_version": "configuration-4-r1.6-observation-accounting-v1",
        "full_run_identity_sha256": ledger["full_run_identity_sha256"],
        "sealed_captures_accounted": len(reports),
        "cases_without_signed_observations": [
            row["task_key"]
            for row in reports
            if row["system_id"] in {"agent", "adaptive_agent"}
            and row["signed_observations"] == 0
        ],
        "captures_without_valid_provider_resource_evidence": sum(
            not row["resource_evidence_valid"] for row in reports
        ),
        "tasks": reports,
        "provider_calls_performed": 0,
    }
    write_json(output / "diagnostics/r1.6-observation-accounting.json", report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "sealed_captures_accounted",
                    "cases_without_signed_observations",
                    "captures_without_valid_provider_resource_evidence",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
