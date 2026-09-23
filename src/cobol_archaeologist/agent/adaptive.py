"""Configuration-3 single-case adaptive D1-D7 investigation agent."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.loop import InvestigationLoop
from cobol_archaeologist.agent.policy import confidence_for_tier, get_hunt
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
from cobol_archaeologist.model.prompt import (
    HUNT_PROMPTS,
    SYSTEM_PROMPT,
    AgentResponse,
    DecisionModel,
    EvidenceLedgerNote,
)
from cobol_archaeologist.model.verify import (
    Entailer,
    VerificationResult,
    VerificationTier,
)
from cobol_archaeologist.schemas import DriftPrediction, DriftType, RegulationClause
from cobol_archaeologist.tool_types import ToolLayer

CONFIG3_AGENT_BUDGET = BudgetSpec(
    max_steps=16,
    max_tool_calls=16,
    max_tokens=98_304,
    wall_clock_timeout_s=1_200,
)

_HYPOTHESIS_POLICY = "\n".join(
    f"- {drift_type}: {policy}" for drift_type, policy in HUNT_PROMPTS.items()
)

ADAPTIVE_SYSTEM_PROMPT = f"""\
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
  live. Inspect the guard definition and its uses. Use `dead_paragraph` only
  for a truly unreachable paragraph; for a disabled guard use an exact source
  literal as the static hook and explain why the action cannot execute.
- Copy every ledger step and observation SHA-256 exactly from the bounded
  command output. Recheck them before the final response.
If the bounded command returns `infrastructure_error`, correct the invocation
and retry while the command and call budget remain available; an invocation
error is not case evidence and is not by itself grounds for a final abstention.
After the first observation, every response must carry the complete current
`evidence_ledger`. Each ledger note names a D1-D7 hypothesis, marks the exact
observation as supports/refutes/context, cites its transcript step and SHA-256,
and explains the evidence bearing. Preserve accepted notes in later turns;
never rewrite, omit, or invent them.

The complete hypothesis policy is:
{_HYPOTHESIS_POLICY}

The host binds the trusted clause and instance identity, applies the selected
class policy guard, and runs the unchanged verifier. Never infer benchmark
answers, edit provenance, mutation history, source formatting, or hidden
annotations. Treat every observation as case-local; no fact carries to a
different case.
"""


EvidenceLedgerEntry = EvidenceLedgerNote


def validate_evidence_ledger(
    notes: Sequence[EvidenceLedgerEntry],
    transcript: Sequence[dict[str, Any]],
    *,
    prior: Sequence[EvidenceLedgerEntry] = (),
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


class AdaptiveOutcome(BaseModel):
    """Typed result for exactly one adaptive case investigation."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: DriftType | None
    finding: DriftPrediction | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification: VerificationResult | None
    verification_tier: VerificationTier | None
    evidence_ledger: list[EvidenceLedgerEntry]
    trajectory: Trajectory
    abstained: bool
    abstention_reason: str | None

    @model_validator(mode="after")
    def _verified_emission_only(self) -> AdaptiveOutcome:
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


def build_adaptive_prompt(
    clause: RegulationClause,
    program_scope: str | None = None,
) -> str:
    """Build a case prompt containing trusted inputs but no benchmark answer."""

    scope = program_scope or "the available corpus"
    return (
        "Investigate this case adaptively across all D1-D7 hypotheses.\n"
        f"Scope: {scope}.\n"
        "Trusted regulation clause:\n"
        f"{clause.model_dump_json(exclude_none=True)}"
    )


def _last_hypothesis(trajectory: Trajectory) -> DriftType | None:
    for response in reversed(trajectory.model_responses):
        if response.prediction is not None:
            return response.prediction.drift_type
    return None


def _last_ledger(trajectory: Trajectory) -> list[EvidenceLedgerEntry]:
    for response in reversed(trajectory.model_responses):
        if response.evidence_ledger:
            return list(response.evidence_ledger)
    return []


def _withhold(trajectory: Trajectory, reason: str) -> Trajectory:
    return Trajectory.model_validate(
        {
            **trajectory.model_dump(),
            "finding": None,
            "abstained": True,
            "abstention_reason": reason,
            "final_answer": f"Abstained: {reason}",
        }
    )


class AdaptiveAgent:
    """Stateless host orchestration for one adaptive benchmark case at a time."""

    def run(
        self,
        *,
        clause: RegulationClause,
        tools: ToolLayer,
        model: DecisionModel,
        program_scope: str | None = None,
        budget: BudgetSpec | None = None,
        entailer: Entailer | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> AdaptiveOutcome:
        accepted_ledger: tuple[EvidenceLedgerEntry, ...] = ()

        def ledger_guard(
            response: AgentResponse,
            transcript: list[dict],
        ) -> list[str]:
            nonlocal accepted_ledger
            notes = response.evidence_ledger
            prediction = response.prediction
            errors = validate_evidence_ledger(
                notes,
                transcript,
                prior=accepted_ledger,
                required_support=(
                    prediction.drift_type if prediction is not None else None
                ),
            )
            if not errors:
                accepted_ledger = tuple(notes)
            return errors

        def render_state(responses: list[AgentResponse]) -> str:
            for prior in reversed(responses):
                if prior.evidence_ledger:
                    payload = [
                        note.model_dump(mode="json") for note in prior.evidence_ledger
                    ]
                    return (
                        "Your prior case-local model-authored evidence ledger "
                        "(preserve and update it):\n"
                        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
                    )
            return ""

        def evidence_guard(
            response: AgentResponse,
            transcript: list[dict],
        ) -> list[str]:
            prediction = response.prediction
            if prediction is None:
                return ["finding response has no prediction"]
            return get_hunt(prediction.drift_type).validate_response(
                response,
                transcript,
                clause,
            )

        trajectory = InvestigationLoop(
            tools,
            model=model,
            budget=budget or CONFIG3_AGENT_BUDGET,
            entailer=entailer,
            clock=clock,
            min_successful_observations_before_abstention=1,
            system_prompt=ADAPTIVE_SYSTEM_PROMPT,
            finding_guard=evidence_guard,
            response_guard=ledger_guard,
            state_renderer=render_state,
        ).run(build_adaptive_prompt(clause, program_scope))

        hypothesis = _last_hypothesis(trajectory)
        ledger = _last_ledger(trajectory)
        if trajectory.abstained:
            return AdaptiveOutcome(
                hypothesis=hypothesis,
                finding=None,
                confidence=None,
                verification=trajectory.verification,
                verification_tier=(
                    trajectory.verification.tier
                    if trajectory.verification is not None
                    else None
                ),
                evidence_ledger=ledger,
                trajectory=trajectory,
                abstained=True,
                abstention_reason=trajectory.abstention_reason,
            )

        if hypothesis is None:
            raise RuntimeError("verified adaptive trajectory has no hypothesis")
        errors = get_hunt(hypothesis).validate_trajectory(trajectory)
        if errors:
            reason = "policy result guard: " + "; ".join(errors)
            trajectory = _withhold(trajectory, reason)
            return AdaptiveOutcome(
                hypothesis=hypothesis,
                finding=None,
                confidence=None,
                verification=trajectory.verification,
                verification_tier=(
                    trajectory.verification.tier
                    if trajectory.verification is not None
                    else None
                ),
                evidence_ledger=ledger,
                trajectory=trajectory,
                abstained=True,
                abstention_reason=reason,
            )

        verification = trajectory.verification
        if verification is None:
            raise RuntimeError("verified adaptive trajectory lost verifier result")
        return AdaptiveOutcome(
            hypothesis=hypothesis,
            finding=trajectory.finding,
            confidence=confidence_for_tier(verification.tier),
            verification=verification,
            verification_tier=verification.tier,
            evidence_ledger=ledger,
            trajectory=trajectory,
            abstained=False,
            abstention_reason=None,
        )
