"""Replay a cached model session through the production detector checks.

A cached session is a list of response payloads: ``tool`` steps followed by a
final ``finding`` or ``abstain``.  Tool steps run against a (stub) tool layer
exactly like the bridge runs them; the final answer goes through
``detector.finalize_case``, the same function the runner uses.
"""

from __future__ import annotations

from typing import Any

from cobol_archaeologist.eval.bridge import ToolLogEntry, summarize
from cobol_archaeologist.eval.detector import (
    CaseOutcome,
    SubmittedCase,
    finalize_case,
)
from cobol_archaeologist.model.verify import Entailer, LexicalEntailer
from cobol_archaeologist.schemas import RegulationClause
from cobol_archaeologist.tool_types import RunInputs, ToolLayer

ALIAS = "drift_900000"
INSTANCE_ID = "drift_910001"


def run_tools(rows: list[dict[str, Any]], tools: ToolLayer) -> list[ToolLogEntry]:
    logs: list[ToolLogEntry] = []
    for row in rows:
        if row["kind"] != "tool":
            continue
        arguments = dict(row.get("arguments") or {})
        call = dict(arguments)
        if row["tool"] == "run_cobol" and isinstance(call.get("inputs"), dict):
            call["inputs"] = RunInputs.model_validate(call["inputs"])
        try:
            summary, truncated = summarize(getattr(tools, row["tool"])(**call))
            error = None
        except Exception as exc:  # noqa: BLE001
            summary, truncated, error = f"{type(exc).__name__}: {exc}", False, (
                f"{type(exc).__name__}: {exc}"
            )
        logs.append(
            ToolLogEntry(
                alias=ALIAS,
                sequence=len(logs) + 1,
                tool=row["tool"],
                arguments=arguments,
                observation_summary=summary,
                observation_truncated=truncated,
                error=error,
                latency_ms=0.0,
            )
        )
    return logs


def submitted_case(
    final: dict[str, Any] | None, logs: list[ToolLogEntry]
) -> SubmittedCase:
    """Convert a cached final payload to the model-facing answer shape."""

    successful = [log.sequence for log in logs if log.error is None]
    if final is None:
        final = {
            "kind": "abstain",
            "thought": "No final answer was produced.",
            "abstention_reason": "no final answer within the budget",
        }
    prediction = final.get("prediction")
    hypothesis = prediction["drift_type"] if prediction else "D7_conformant"
    if "evidence_ledger" in final:
        ledger = [
            {key: value for key, value in note.items() if key != "observation_sha256"}
            for note in final["evidence_ledger"]
        ]
    else:
        bearing = "supports" if final["kind"] == "finding" else "context"
        ledger = [
            {
                "observation_step": step,
                "hypothesis": hypothesis,
                "bearing": bearing,
                "rationale": "Cached investigation observation.",
            }
            for step in successful
        ]
    submitted_prediction = None
    if prediction:
        submitted_prediction = {
            key: value
            for key, value in prediction.items()
            if key not in {"instance_id", "regulation_clause"}
        }
        submitted_prediction.setdefault("target_path", None)
    return SubmittedCase.model_validate(
        {
            "alias": ALIAS,
            "evidence_ledger": ledger,
            "response": {
                "kind": final["kind"],
                "thought": final.get("thought", ""),
                "prediction": submitted_prediction,
                "claim": final.get("claim"),
                "exec_probe": final.get("exec_probe"),
                "static_claim": final.get("static_claim"),
                "abstention_reason": final.get("abstention_reason"),
                "final_answer": final.get("final_answer") or "",
            },
        }
    )


def replay(
    rows: list[dict[str, Any]],
    *,
    clause: RegulationClause,
    tools: ToolLayer,
    entailer: Entailer | None = None,
    program_scope: str = "CASE",
) -> CaseOutcome:
    logs = run_tools(rows, tools)
    final = next(
        (row for row in reversed(rows) if row["kind"] in {"finding", "abstain"}),
        None,
    )
    return finalize_case(
        submitted_case(final, logs),
        clause=clause,
        program_scope=program_scope,
        instance_id=INSTANCE_ID,
        logs=logs,
        tools=tools,
        entailer=entailer or LexicalEntailer(),
        token_count=0,
        token_count_recorded=False,
        model_id="offline-replay",
    )
