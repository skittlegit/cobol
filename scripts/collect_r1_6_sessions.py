"""Seal finished isolated R1.6 sessions, audit new results, and checkpoint.

No model is invoked. Already sealed results and already rejected exact finals
are skipped; all new captures use the existing schema-first session sealer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from cobol_archaeologist.eval.config4_runner import Config4RunPreparation

NAME = re.compile(
    r"^/root/r16_(agent|adaptive|plain_llm|rag_dense|rag_reranker|oracle_slice)_(\d+)(?:_attempt\d+)?$"
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    prep = Config4RunPreparation.model_validate_json(
        (output / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    handoff = json.loads(
        (output / "full/r1.5-handoff.json").read_text(encoding="utf-8")
    )
    allowed = set(handoff["full_run_pending_task_keys"])
    by_ordinal = {(task.system_id, task.ordinal): task for task in prep.tasks}
    ledger_path = output / "full/r1.6-captures.json"
    ledger = (
        json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger_path.exists()
        else {
            "schema_version": "configuration-4-r1.6-captures-v1",
            "full_run_identity_sha256": handoff["full_run_identity_sha256"],
            "captures": [],
        }
    )
    if ledger["full_run_identity_sha256"] != handoff["full_run_identity_sha256"]:
        raise RuntimeError("capture ledger belongs to another full run")
    captured_keys = {
        capture.get("task_key")
        or by_ordinal[(capture["system_id"], capture["ordinal"])].task_key
        for capture in ledger["captures"]
    }
    changed = []
    for session in sorted(args.sessions.glob("*.jsonl")):
        with session.open(encoding="utf-8") as stream:
            metadata = json.loads(stream.readline())
        source = metadata["payload"].get("source", {})
        if not isinstance(source, dict):
            continue
        name = source.get("subagent", {}).get("thread_spawn", {}).get("agent_path", "")
        match = NAME.fullmatch(name)
        if match is None:
            continue
        system = "adaptive_agent" if match[1] == "adaptive" else match[1]
        ordinal = int(match[2])
        task = by_ordinal[(system, ordinal)]
        if task.task_key not in allowed:
            raise RuntimeError(
                "worker session references an already completed handoff key"
            )
        if task.task_key in captured_keys:
            continue
        rows = [
            json.loads(line)
            for line in session.read_text(encoding="utf-8").splitlines()
        ]
        final = next(
            (
                row["payload"]["content"][0]["text"]
                for row in reversed(rows)
                if row.get("payload", {}).get("phase") == "final_answer"
            ),
            None,
        )
        if final is None:
            continue
        digest = hashlib.sha256(final.encode("utf-8")).hexdigest()
        diagnostic = (
            output / "rejected-finals" / f"{system}-{ordinal:03d}-{digest}.json"
        )
        if diagnostic.exists():
            continue
        contexts = [row["payload"] for row in rows if row["type"] == "turn_context"]
        if not contexts or any(
            c["model"] != "gpt-6-luna" or c["effort"] != "max" for c in contexts
        ):
            raise RuntimeError("evaluator session identity differs from frozen R1.6")
        command = [
            sys.executable,
            str(root / "scripts/seal_config4_session.py"),
            "--output",
            str(output),
            "--mode",
            "full",
            "--system",
            system,
            "--ordinal",
            str(ordinal),
            "--session",
            str(session),
        ]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        if result.returncode:
            changed.append(
                {
                    "system_id": system,
                    "ordinal": ordinal,
                    "status": "CAPTURE_REJECTED",
                    "error": result.stderr[-1800:],
                }
            )
            continue
        audit = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/audit_config4_partial.py"),
                "--output",
                str(output),
                "--system",
                system,
                "--ordinal",
                str(ordinal),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(audit.stdout)
        if report["tasks_audited"] != 1:
            raise RuntimeError("new capture audit did not cover exactly one task")
        observed = report["tasks"][0]
        audit_path = output / "full/r1.6-audits" / f"{system}-{ordinal:03d}.json"
        write_json(audit_path, report)
        capture = {
            "system_id": system,
            "ordinal": ordinal,
            "task_key": task.task_key,
            "task_name": name,
            "session_file": session.name,
            "session_sha256": hashlib.sha256(session.read_bytes()).hexdigest(),
            "final_sha256": digest,
            "host_audit": {
                key: observed[key]
                for key in (
                    "infrastructure_errors",
                    "unverified_emissions",
                    "contract_repairs",
                )
            },
            "host_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
            "provider_resource_telemetry": "not_recorded",
            "status": "SEALED_AND_REPLAYED",
        }
        ledger["captures"].append(capture)
        captured_keys.add(task.task_key)
        write_json(ledger_path, ledger)
        changed.append(capture)
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/checkpoint_r1_6.py"),
            "--output",
            str(output),
            "--limit",
            str(args.limit),
            *[value for key in args.exclude for value in ("--exclude", key)],
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    state = json.loads(result.stdout)
    window_path = output / "diagnostics/r1.6-window.json"
    if window_path.exists():
        window = json.loads(window_path.read_text(encoding="utf-8"))
        window.update(
            {
                key: state[key]
                for key in (
                    "sealed_full_run_tasks",
                    "pending_full_run_tasks",
                    "r1_6_sealed_tasks",
                )
            }
        )
        write_json(window_path, window)
    for name in ("STATUS.md", "FLAGS.md"):
        path = root / name
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"\b\d+/610\b", f"{state['sealed_full_run_tasks']}/610", text)
        text = re.sub(
            r"\*\*\d+\*\* pending for R1\.6",
            f"**{state['pending_full_run_tasks']}** pending for R1.6",
            text,
        )
        text = re.sub(
            r"\b\d+ full-run keys remain",
            f"{state['pending_full_run_tasks']} full-run keys remain",
            text,
        )
        text = re.sub(
            r"resume \d+ immutable full-run keys",
            f"resume {state['pending_full_run_tasks']} immutable full-run keys",
            text,
        )
        text = re.sub(
            r"run has \d+ sealed tasks overall",
            f"run has {state['sealed_full_run_tasks']} sealed tasks overall",
            text,
        )
        path.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"new_results": changed, **state}, indent=2))


if __name__ == "__main__":
    main()
