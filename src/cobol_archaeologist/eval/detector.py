"""The drift detector: one adaptive Codex investigation per case.

The model investigates a case through the tool bridge, may check draft
answers with ``check_finding``, and submits one final answer.  The host then
binds the trusted clause and identity, rebuilds the evidence ledger with
host-computed observation hashes, applies the class policy guard, and runs the
verifier.  Anything that fails a check becomes an abstention.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.policy import confidence_for_tier, get_hunt
from cobol_archaeologist.agent.trajectory import BudgetSpec, ToolCall, Trajectory
from cobol_archaeologist.eval.bridge import (
    BRIDGE_MODULE,
    CHECK_OPERATION,
    MAX_CHECKS,
    MAX_TOOL_CALLS,
    ToolLogEntry,
)
from cobol_archaeologist.model.prompt import (
    HUNT_PROMPTS,
    SYSTEM_PROMPT,
    AgentResponse,
    EvidenceLedgerNote,
)
from cobol_archaeologist.model.verify import (
    Entailer,
    ExecProbe,
    Finding,
    StaticClaim,
    VerificationResult,
    VerificationTier,
    verify,
)
from cobol_archaeologist.schemas import (
    DriftPrediction,
    DriftType,
    Labels,
    RegulationClause,
    SourceLocus,
)
from cobol_archaeologist.tool_types import ToolLayer

PROMPT_VERSION = "detector-v3"
DETECTOR_BUDGET = BudgetSpec(
    max_steps=MAX_TOOL_CALLS,
    max_tool_calls=MAX_TOOL_CALLS,
    max_tokens=4_000_000,
    wall_clock_timeout_s=1_800,
)
ALIAS_PATTERN = r"^drift_9\d{5}$"


_HYPOTHESIS_POLICY = "\n".join(
    f"- {drift_type}: {policy}" for drift_type, policy in HUNT_PROMPTS.items()
)

INVESTIGATION_POLICY = f"""\
{SYSTEM_PROMPT}
This is one adaptive investigation, not seven independent hunts. Maintain a
single evidence ledger from the accumulated bounded tool observations. At
each turn, compare the viable D1-D7 hypotheses, choose the next tool for the
largest useful uncertainty reduction, and revise or reject hypotheses when
observations conflict with them. Do not commit to a class before its evidence
requirements are met. Emit at most one final finding for the best-supported
hypothesis, or abstain when the bounded evidence cannot support any class.
Before emitting, perform this class-arbitration preflight:
- Enumerate every typed locus found for the same regulated condition before
  choosing D1. If two reachable typed loci produce conflicting outcomes,
  choose D3 rather than selecting one locus as a stale D1 value.
- Choose D2 when the specific regulated behavior or required violation outcome
  is absent. Inspect the relevant paragraph, scoped grep, and data slice,
  but distinguish positive surrounding control flow from positive evidence of
  the required outcome itself. A present compliant branch does not cure a
  missing breach/overdue/denial branch. Do not invent an unstated date
  derivation, preprocessing step, or implementation mechanism as a missing
  rule. If complete positive code evidence matches the clause and no supported
  drift remains, consider D7.
  Treat a one-sided state machine as incomplete when the regulated outcome for
  the other side is absent: `days <= 30 -> UPDATE` without an explicit
  `days > 30 -> BREACH` outcome is D2, and `today <= due -> OK` without an
  explicit overdue outcome is D2. A zero-day `NEW` special case does not
  implement a required seven-day SLA. Do not call these partial machines D7.
- Choose D3 when reachable source behavior positively contradicts the trusted
  clause. Two source loci are required only for an internal source conflict;
  one typed computation can contradict the clause directly. For a required
  exclusion, accepting a regulated amount and then computing the base without
  excluding it is contradictory, not conformant-by-absence.
  A validation rule that detects the regulated violation and sets a denial or
  invalid state, followed by a reachable action that ignores or bypasses that
  state, is also D3: the implemented validation and action conflict. Do not
  relabel that case D2 merely because the final gate is malformed or absent.
  Reserve D2 for a required outcome that is absent without an existing source
  state or action that positively conflicts with the requirement.
- Choose D4 only for an enum_set reference collection, and quote at least one
  complete canonical missing or extra enum member verbatim, including its
  prefixes and punctuation, in `prediction.rationale`.
- For D7, put the positive source location in `code_locus`, but set
  `labels.program_level` and `labels.paragraph_level` to `conformant` and set
  `labels.line_level` to an empty list. D7 line labels identify drift and must
  therefore stay empty. When the clause current value is composite, set
  `target_path` to the exact matching non-composite leaf.
- Interpret a comparator together with the branch action and control-flow
  polarity. Do not call D5 from a token-only comparison between a clause's
  typed comparator and a source predicate. In an elapsed-window state machine,
  `elapsed > limit` can be the conformant transition after the full allowed
  window, while `elapsed >= limit` can fire one boundary unit early. Trace the
  resulting action and use a boundary probe when possible before choosing D5.
  Apply these exact elapsed-window checks: `delay > 7` is conformant for a
  seven-day allowed window and `delay >= 7` is one unit early; `elapsed > 30`
  is conformant for an at-most-30-day window and `elapsed >= 30` is early;
  `notice >= 30` is conformant for an at-least-30-day requirement and
  `notice > 30` is late. Do not cancel an early transition merely because a
  downstream arithmetic expression happens to evaluate to zero at the edge.
- Choose D6 when the relevant compliance action is unreachable, including a
  reachable paragraph whose compliance branch is disabled by an always-false
  or default-off flag. A paragraph caller does not make guarded statements
  live. Inspect the guard definition and every assignment to the guard field:
  grep the field name across all programs in scope, because the value may be
  set by a MOVE in another program or a shared copybook. If every value the
  field can hold keeps the guard false, the action is dead: that is D6, not
  D2. D2 means the behavior is absent from the code; D6 means it is present
  but cannot execute. Use `dead_paragraph` only for a truly unreachable
  paragraph; for a disabled guard use an exact source literal (for example
  the VALUE or MOVE literal that disables it) as the static hook.
- Before choosing D2, search for the required outcome itself (grep its
  literal, status value, or paragraph name, and slice the variable that would
  carry it). If the outcome exists and is reachable, D2 is wrong: compare the
  implementation with the clause for D1, D3, D5, or D7 instead.
- Judge only against the supplied clause version and its `current_value`.
  The same code can be conformant under one version of a regulation and
  drifted under another, so never assume which version the code was written
  for; compare the code with the version you were given.
If the command returns `infrastructure_error`, correct the invocation and
retry while the call budget remains; an invocation error is not case evidence
and is not by itself grounds for abstention.

The complete hypothesis policy is:
{_HYPOTHESIS_POLICY}

The host binds the trusted clause and instance identity, applies the selected
class policy guard, and runs the unchanged verifier. Never infer benchmark
answers, edit provenance, mutation history, source formatting, or hidden
annotations. Treat every observation as case-local; no fact carries to a
different case.
"""


def validate_evidence_ledger(
    notes: Sequence[EvidenceLedgerNote],
    transcript: Sequence[dict[str, Any]],
    *,
    prior: Sequence[EvidenceLedgerNote] = (),
    required_support: DriftType | None = None,
) -> list[str]:
    """Validate model-authored notes against exact successful observations."""

    successful = {
        int(step["step"]): step
        for step in transcript
        if not step.get("error") and step.get("observation_summary")
    }
    errors: list[str] = []
    if not successful and notes:
        errors.append("ledger cites evidence before any successful observation")
    if successful and not notes:
        errors.append("complete evidence ledger missing after observation")
    keys: set[tuple] = set()
    for note in notes:
        key = (
            note.observation_step,
            note.observation_sha256,
            note.hypothesis,
            note.bearing,
            note.rationale,
        )
        if key in keys:
            errors.append("duplicate evidence ledger note")
        keys.add(key)
        step = successful.get(note.observation_step)
        if step is None:
            errors.append(
                f"ledger step {note.observation_step} is not a successful observation"
            )
            continue
        digest = hashlib.sha256(
            str(step["observation_summary"]).encode("utf-8")
        ).hexdigest()
        if note.observation_sha256 != digest:
            errors.append(
                f"ledger step {note.observation_step} observation hash differs"
            )
    prior_keys = {
        (
            note.observation_step,
            note.observation_sha256,
            note.hypothesis,
            note.bearing,
            note.rationale,
        )
        for note in prior
    }
    if not prior_keys.issubset(keys):
        errors.append("accepted evidence ledger notes were omitted or rewritten")
    if required_support is not None and not any(
        note.hypothesis == required_support and note.bearing == "supports"
        for note in notes
    ):
        errors.append("finding lacks a supporting ledger note for its hypothesis")
    return errors


def _last_ledger(trajectory: Trajectory) -> list[EvidenceLedgerNote]:
    for response in reversed(trajectory.model_responses):
        if response.evidence_ledger:
            return list(response.evidence_ledger)
    return []


class CaseOutcome(BaseModel):
    """Typed result for exactly one adaptive case investigation."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: DriftType | None
    finding: DriftPrediction | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification: VerificationResult | None
    verification_tier: VerificationTier | None
    evidence_ledger: list[EvidenceLedgerNote]
    trajectory: Trajectory
    abstained: bool
    abstention_reason: str | None

    @model_validator(mode="after")
    def _verified_emission_only(self) -> CaseOutcome:
        if self.evidence_ledger != _last_ledger(self.trajectory):
            raise ValueError("adaptive ledger must be the model-authored final ledger")
        if self.abstained:
            if self.finding is not None:
                raise ValueError("an abstained adaptive run cannot emit a finding")
            if not self.abstention_reason:
                raise ValueError("an abstained adaptive run requires a reason")
            if self.verification != self.trajectory.verification:
                raise ValueError("adaptive verification must match its trajectory")
            expected_tier = (
                self.verification.tier if self.verification is not None else None
            )
            if self.verification_tier != expected_tier:
                raise ValueError("adaptive verification tier is inconsistent")
            if not self.trajectory.abstained:
                raise ValueError("adaptive abstention must match its trajectory")
            if self.abstention_reason != self.trajectory.abstention_reason:
                raise ValueError("adaptive abstention reason must match trajectory")
            if self.confidence is not None:
                raise ValueError("adaptive abstention cannot carry confidence")
            return self
        successful = {
            step.step: step
            for step in self.trajectory.steps
            if step.error is None and step.observation_summary
        }
        for entry in self.evidence_ledger:
            step = successful.get(entry.observation_step)
            if step is None:
                raise ValueError("adaptive ledger cites a missing observation")
            digest = hashlib.sha256(
                step.observation_summary.encode("utf-8")
            ).hexdigest()
            if digest != entry.observation_sha256:
                raise ValueError("adaptive ledger observation hash mismatch")
        if self.finding is None or self.hypothesis != self.finding.drift_type:
            raise ValueError("a successful adaptive run requires its hypothesis")
        if (
            self.verification is None
            or not self.verification.verified
            or self.verification_tier != self.verification.tier
        ):
            raise ValueError("an adaptive finding requires its verified tier")
        if self.confidence is None:
            raise ValueError("an adaptive finding requires confidence")
        if (
            self.finding != self.trajectory.finding
            or self.verification != self.trajectory.verification
            or self.trajectory.abstained
        ):
            raise ValueError("adaptive output must match its verified trajectory")
        if not any(
            entry.bearing == "supports" and entry.hypothesis == self.hypothesis
            for entry in self.evidence_ledger
        ):
            raise ValueError("an adaptive finding requires cited supporting evidence")
        return self


# --------------------------------------------------------------------------
# Model-facing answer shape (trusted identity and clause are host-attached)
# --------------------------------------------------------------------------


class SubmittedCodeLocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loci: list[SourceLocus] = Field(min_length=1)
    slice_vars: list[str]
    is_interprocedural: bool


class SubmittedPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_locus: SubmittedCodeLocus
    drift_type: DriftType
    target_path: str | None
    labels: Labels
    rationale: str = Field(min_length=1)

    def attach_inputs(
        self, *, instance_id: str, clause: RegulationClause
    ) -> DriftPrediction:
        payload = self.model_dump()
        target_path = payload.get("target_path")
        current = clause.current_value
        if isinstance(target_path, str) and current is not None:
            if current.kind == "composite":
                for prefix in ("current_value.", "value."):
                    target_path = target_path.removeprefix(prefix)
            elif target_path in {"value", "current_value", "current_value.value"}:
                # A wrapper name for the already-selected scalar leaf.
                target_path = None
            payload["target_path"] = target_path
        return DriftPrediction(
            instance_id=instance_id, regulation_clause=clause, **payload
        )


class SubmittedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["finding", "abstain"]
    thought: str
    prediction: SubmittedPrediction | None
    claim: str | None = Field(
        description=(
            "Clause-grounded regulatory proposition entailed by the cited "
            "clause; never a COBOL implementation or drift assertion."
        )
    )
    exec_probe: ExecProbe | None
    static_claim: StaticClaim | None
    abstention_reason: str | None
    final_answer: str

    @model_validator(mode="after")
    def _exclusive_shape(self) -> SubmittedResponse:
        if self.kind == "finding":
            if self.prediction is None or not self.claim:
                raise ValueError("a finding requires prediction and claim")
            if self.abstention_reason is not None:
                raise ValueError("a finding cannot carry an abstention reason")
        elif not self.abstention_reason:
            raise ValueError("an abstention requires a reason")
        return self


class SubmittedLedgerNote(BaseModel):
    """A ledger note cites a tool call by sequence; the host adds its hash."""

    model_config = ConfigDict(extra="forbid")

    observation_step: int = Field(ge=1)
    hypothesis: DriftType
    bearing: Literal["supports", "refutes", "context"]
    rationale: str = Field(min_length=1)


class SubmittedCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(pattern=ALIAS_PATTERN)
    evidence_ledger: list[SubmittedLedgerNote]
    response: SubmittedResponse


class DetectorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SubmittedCase] = Field(min_length=1, max_length=1)


def bind_response(
    submitted: SubmittedResponse,
    *,
    instance_id: str,
    clause: RegulationClause,
    token_count: int,
    token_count_recorded: bool = True,
    prebinding_error: str | None = None,
) -> AgentResponse:
    """Attach trusted inputs; a finding that cannot bind becomes an abstention."""

    raw = submitted.model_dump_json()
    thought = submitted.thought.strip() or (
        submitted.claim or submitted.abstention_reason or "No reasoning supplied."
    )
    final_answer = submitted.final_answer.strip() or (
        f"Finding: {submitted.claim}"
        if submitted.kind == "finding"
        else f"Abstained: {submitted.abstention_reason}"
    )

    def abstain(reason: str) -> AgentResponse:
        return AgentResponse(
            kind="abstain",
            thought=thought,
            abstention_reason=reason,
            final_answer=f"Abstained: {reason}",
            token_count=token_count,
            token_count_recorded=token_count_recorded,
            raw_provider_text=raw,
        )

    if submitted.kind == "abstain":
        return abstain(submitted.abstention_reason or "model abstained").model_copy(
            update={"final_answer": final_answer}
        )
    if prebinding_error is not None:
        return abstain(
            f"prediction failed host-input binding; refusing emission: {prebinding_error}"
        )
    assert submitted.prediction is not None
    try:
        prediction = submitted.prediction.attach_inputs(
            instance_id=instance_id, clause=clause
        )
    except ValueError as exc:
        return abstain(
            f"prediction failed host-input binding; refusing emission: {exc}"
        )
    return AgentResponse(
        kind="finding",
        thought=thought,
        prediction=prediction,
        claim=submitted.claim,
        exec_probe=submitted.exec_probe,
        static_claim=submitted.static_claim,
        final_answer=final_answer,
        token_count=token_count,
        token_count_recorded=token_count_recorded,
        raw_provider_text=raw,
    )


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------


def build_prompt(
    *, alias: str, clause: RegulationClause, program_scope: str, tool_command: str
) -> str:
    visible = json.dumps(
        {
            "alias": alias,
            "program_scope": program_scope,
            "clause": clause.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""\
You are a COBOL regulatory-compliance detector. Investigate exactly one case
against its regulation clause and decide which of D1-D7 applies, keeping one
evolving hypothesis ledger. Benchmark labels, generation history, scoring
data, and other cases are not available and must not be inferred.

Gather source evidence only with this command (one call per invocation):
  {tool_command} {alias} TOOL --arguments 'JSON_OBJECT'
TOOL and its JSON arguments: read_program {{"program":"..."}};
read_paragraph {{"program":"...","name":"..."}}; find_callers and find_callees
{{"program":"...","para":"..."}}; trace_variable and slice_on
{{"var":"...","program":"..."}}; resolve_copybook {{"name":"..."}};
get_data_layout {{"record":"..."}}; grep {{"pattern":"..."}};
run_cobol {{"snippet":"...","inputs":null}}.
Each call returns a `sequence` number. You have at most {MAX_TOOL_CALLS} tool
calls. Do not read files directly or inspect directories, git data,
timestamps, comments as edit cues, formatting, or identifier style.

Before submitting, check your draft final answer with:
  {tool_command} {alias} {CHECK_OPERATION} --arguments 'DRAFT_JSON'
where DRAFT_JSON is the object you intend to submit for this alias, without
the "alias" key (keys: evidence_ledger, response). It runs the same ledger,
policy-guard, and verifier checks the host applies to your final answer and
returns `accepted` plus the exact `rejection` reason. If a finding is
rejected, fix the cited problem (for example the rationale, static hook, line
labels, or the claim wording) and check again; you may run at most
{MAX_CHECKS} checks. Never change your class only to pass a check; abstain if
the evidence does not support any class.

Evidence ledger: each note cites one successful tool call by its `sequence`
number in `observation_step`, names a D1-D7 hypothesis, marks it
supports/refutes/context, and explains the bearing. The host attaches the
observation hashes; do not write hashes.

The host attaches the case identity and the trusted clause; your prediction
contains only the fields in the output schema. Return exactly one result for
alias {alias}.

{INVESTIGATION_POLICY}

Detector-visible case:
{visible}
"""


# --------------------------------------------------------------------------
# Host finalization
# --------------------------------------------------------------------------


def _steps(logs: Sequence[ToolLogEntry], alias: str) -> list[ToolCall]:
    relevant = sorted(
        (entry for entry in logs if entry.alias == alias), key=lambda e: e.sequence
    )
    sequences = [entry.sequence for entry in relevant]
    if len(sequences) != len(set(sequences)):
        raise ValueError("tool log contains duplicate sequences")
    if len(relevant) > DETECTOR_BUDGET.max_tool_calls:
        raise ValueError("tool log exceeds the tool budget")
    return [
        ToolCall(
            step=entry.sequence,
            tool=entry.tool,
            arguments=entry.arguments,
            observation_summary=entry.observation_summary,
            observation_truncated=entry.observation_truncated,
            error=entry.error,
            latency_ms=entry.latency_ms,
        )
        for entry in relevant
    ]


def _transcript(steps: Sequence[ToolCall]) -> list[dict[str, Any]]:
    return [
        {
            "step": step.step,
            "tool": step.tool,
            "arguments": step.arguments,
            "observation_summary": step.observation_summary,
            "observation_truncated": step.observation_truncated,
            "error": step.error,
        }
        for step in steps
    ]


def host_ledger(
    notes: Sequence[SubmittedLedgerNote], steps: Sequence[ToolCall]
) -> tuple[list[EvidenceLedgerNote], list[str]]:
    """Attach host-computed hashes to model-cited observations."""

    by_step = {
        step.step: step
        for step in steps
        if step.error is None and step.observation_summary
    }
    ledger: list[EvidenceLedgerNote] = []
    errors: list[str] = []
    for note in notes:
        step = by_step.get(note.observation_step)
        if step is None:
            errors.append(
                f"ledger step {note.observation_step} is not a successful observation"
            )
            continue
        ledger.append(
            EvidenceLedgerNote(
                observation_step=note.observation_step,
                observation_sha256=hashlib.sha256(
                    step.observation_summary.encode("utf-8")
                ).hexdigest(),
                hypothesis=note.hypothesis,
                bearing=note.bearing,
                rationale=note.rationale,
            )
        )
    return ledger, errors


def _abstained(
    *,
    response: AgentResponse,
    question: str,
    steps: list[ToolCall],
    reason: str,
    model_id: str,
    verification=None,
    budget_exhausted: bool = False,
) -> CaseOutcome:
    trajectory = Trajectory(
        question=question,
        steps=steps,
        model_responses=[response],
        verification=verification,
        finding=None,
        abstained=True,
        abstention_reason=reason,
        budget=DETECTOR_BUDGET,
        budget_exhausted=budget_exhausted,
        tokens_used=response.token_count,
        token_usage_recorded=response.token_count_recorded,
        contract_repairs=0,
        final_answer=f"Abstained: {reason}",
        model_id=model_id,
        seed=None,
    )
    return CaseOutcome(
        hypothesis=(
            response.prediction.drift_type if response.prediction is not None else None
        ),
        finding=None,
        confidence=None,
        verification=verification,
        verification_tier=verification.tier if verification is not None else None,
        evidence_ledger=list(response.evidence_ledger),
        trajectory=trajectory,
        abstained=True,
        abstention_reason=reason,
    )


def finalize_case(
    submitted: SubmittedCase,
    *,
    clause: RegulationClause,
    program_scope: str,
    instance_id: str,
    logs: Sequence[ToolLogEntry],
    tools: ToolLayer,
    entailer: Entailer,
    token_count: int,
    token_count_recorded: bool = True,
    model_id: str = "gpt-6-luna",
) -> CaseOutcome:
    """Bind trusted inputs, rebuild the ledger, then apply guards and verifier."""

    steps = _steps(logs, submitted.alias)
    transcript = _transcript(steps)
    question = build_prompt(
        alias=submitted.alias,
        clause=clause,
        program_scope=program_scope,
        tool_command=f"python -m {BRIDGE_MODULE}",
    )
    ledger, ledger_binding_errors = host_ledger(submitted.evidence_ledger, steps)
    response = bind_response(
        submitted.response,
        instance_id=instance_id,
        clause=clause,
        token_count=token_count,
        token_count_recorded=token_count_recorded,
    ).model_copy(update={"evidence_ledger": ledger})

    def abstain(reason: str, **kwargs) -> CaseOutcome:
        return _abstained(
            response=response,
            question=question,
            steps=steps,
            reason=reason,
            model_id=model_id,
            **kwargs,
        )

    if token_count_recorded and token_count > DETECTOR_BUDGET.max_tokens:
        return abstain("token budget exhausted", budget_exhausted=True)
    prediction = response.prediction
    ledger_errors = ledger_binding_errors + validate_evidence_ledger(
        response.evidence_ledger,
        transcript,
        required_support=prediction.drift_type if prediction is not None else None,
    )
    if ledger_errors:
        return abstain("evidence ledger: " + "; ".join(dict.fromkeys(ledger_errors)))
    if not any(step.error is None and step.observation_summary for step in steps):
        return abstain("evidence minimum not met: no successful observation")
    if response.kind == "abstain":
        return abstain(response.abstention_reason or "model abstained")
    assert prediction is not None
    hunt = get_hunt(prediction.drift_type)
    guard_errors = hunt.validate_response(response, transcript, clause)
    if guard_errors:
        return abstain("policy evidence guard: " + "; ".join(guard_errors))
    finding = Finding.from_prediction(prediction, claim=response.claim).model_copy(
        update={
            "exec_probe": response.exec_probe,
            "static_claim": response.static_claim,
        }
    )
    try:
        verification = verify(finding, tools, entailer=entailer)
    except Exception as exc:  # noqa: BLE001
        return abstain(
            f"verification unavailable; refusing emission: {type(exc).__name__}: {exc}"
        )
    if not verification.verified:
        return abstain(
            verification.rejected_reason or "finding was not verified",
            verification=verification,
        )
    trajectory = Trajectory(
        question=question,
        steps=steps,
        model_responses=[response],
        verification=verification,
        finding=prediction,
        abstained=False,
        abstention_reason=None,
        budget=DETECTOR_BUDGET,
        budget_exhausted=False,
        tokens_used=token_count,
        token_usage_recorded=token_count_recorded,
        contract_repairs=0,
        final_answer=response.final_answer or verification.evidence,
        model_id=model_id,
        seed=None,
    )
    result_errors = hunt.validate_trajectory(trajectory)
    if result_errors:
        return abstain(
            "policy result guard: " + "; ".join(result_errors),
            verification=verification,
        )
    return CaseOutcome(
        hypothesis=prediction.drift_type,
        finding=prediction,
        confidence=confidence_for_tier(verification.tier),
        verification=verification,
        verification_tier=verification.tier,
        evidence_ledger=list(response.evidence_ledger),
        trajectory=trajectory,
        abstained=False,
        abstention_reason=None,
    )
