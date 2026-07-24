"""Replay and evidence-path assessment for T4.3."""

from __future__ import annotations

import json

from cobol_archaeologist.eval.schemas import (
    EvaluationRecord,
    TrajectoryAssessment,
)

_REQUIRED_TOOLS = {
    "D1_stale_threshold": ({"read_paragraph", "resolve_copybook", "grep"}, 1),
    "D2_missing_rule": ({"grep", "find_callers", "find_callees", "slice_on"}, 4),
    "D3_contradictory": ({"read_paragraph"}, 2),
    "D4_stale_reference_data": ({"resolve_copybook"}, 1),
    "D5_boundary_error": ({"read_paragraph"}, 1),
    "D6_dead_code": ({"read_paragraph"}, 1),
    "D7_conformant": ({"read_paragraph"}, 1),
}
_SHORTCUT_TOKENS = (
    ".git",
    "git log",
    "git diff",
    "mtime",
    "modified time",
    "provenance.mutation",
    "gold_rationale",
    "drift_type",
)


def _required_path_ok(record: EvaluationRecord) -> bool:
    if record.trajectory is None or record.prediction is None:
        return False
    tools = [step.tool for step in record.trajectory.steps if not step.error]
    required, minimum = _REQUIRED_TOOLS[record.prediction.drift_type]
    if record.prediction.drift_type == "D1_stale_threshold":
        return any(tool in required for tool in tools)
    if record.prediction.drift_type == "D3_contradictory":
        return tools.count("read_paragraph") >= minimum
    return required.issubset(tools) and len(tools) >= minimum


def _code_fact_ok(record: EvaluationRecord) -> bool:
    if record.trajectory is None or record.prediction is None:
        return False
    drift_type = record.prediction.drift_type
    if drift_type == "D6_dead_code":
        return bool(
            record.verification
            and record.verification.tier is not None
            and int(record.verification.tier) == 2
            and "forest_roots + reachable_from" in record.verification.evidence
        )
    if drift_type == "D2_missing_rule":
        return bool(
            {
                (line.program, line.file, line.line)
                for line in record.prediction.labels.line_level
            }
            & {
                (line.program, line.file, line.line)
                for line in record.gold.labels.line_level
            }
        )
    if drift_type == "D7_conformant":
        return _required_path_ok(record) and not record.prediction.labels.line_level
    predicted = {
        (line.program, line.file, line.line)
        for line in record.prediction.labels.line_level
    }
    gold = {
        (line.program, line.file, line.line) for line in record.gold.labels.line_level
    }
    if not predicted & gold:
        return False
    observations = " ".join(
        step.observation_summary for step in record.trajectory.steps
    ).lower()
    return any(
        program.lower() in observations and str(line) in observations
        for program, _file, line in predicted & gold
    )


def assess_trajectory(record: EvaluationRecord) -> TrajectoryAssessment:
    reasons: list[str] = []
    trajectory = record.trajectory
    if trajectory is None:
        return TrajectoryAssessment(
            instance_id=record.instance_id,
            replayable=False,
            evidence_path_ok=False,
            code_fact_ok=False,
            budget_ok=False,
            shortcut_free=True,
            reasons=["no trajectory"],
        )
    try:
        replayable = trajectory.model_validate_json(trajectory.model_dump_json()) == trajectory
    except (ValueError, TypeError):
        replayable = False
    if not replayable:
        reasons.append("trajectory does not round-trip")
    evidence_path_ok = _required_path_ok(record)
    if not evidence_path_ok:
        reasons.append("class-required evidence path is incomplete")
    code_fact_ok = _code_fact_ok(record)
    if not code_fact_ok:
        reasons.append("cited code fact is not grounded at a gold typed locus")
    budget_ok = (
        len(trajectory.steps) <= trajectory.budget.max_tool_calls
        and len(trajectory.model_responses) <= trajectory.budget.max_steps
        and sum(response.token_count for response in trajectory.model_responses)
        == trajectory.tokens_used
        and trajectory.tokens_used <= trajectory.budget.max_tokens
    )
    if not budget_ok:
        reasons.append("recorded budget totals do not recompute")
    serialized_steps = json.dumps(
        [step.model_dump(mode="json") for step in trajectory.steps],
        sort_keys=True,
    ).lower()
    shortcut_free = not any(token in serialized_steps for token in _SHORTCUT_TOKENS)
    if not shortcut_free:
        reasons.append("forbidden shortcut cue appears in tool trace")
    if trajectory.finding is not None and (
        trajectory.verification is None or not trajectory.verification.verified
    ):
        reasons.append("unverified finding in trajectory")
        replayable = False
    return TrajectoryAssessment(
        instance_id=record.instance_id,
        replayable=replayable,
        evidence_path_ok=evidence_path_ok,
        code_fact_ok=code_fact_ok,
        budget_ok=budget_ok,
        shortcut_free=shortcut_free,
        reasons=reasons,
    )


def assess_all(records: list[EvaluationRecord]) -> list[TrajectoryAssessment]:
    return [assess_trajectory(record) for record in records]
