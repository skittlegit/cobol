"""Detection policy and deterministic decision seam (Track C, T3.4/T3.5).

The investigation loop depends on :class:`DecisionModel`, not on a provider
SDK.  Production adapters can implement that protocol; offline gates use
:class:`CachedDecisionModel`, whose responses are committed JSON.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.model.verify import ExecProbe, StaticClaim
from cobol_archaeologist.schemas import DriftPrediction, RegulationClause

MODEL_ID = "claude-3-5-sonnet-20241022"
MODEL_TEMPERATURE = 0.0
MODEL_SEED = 0

ToolName = Literal[
    "read_paragraph",
    "read_program",
    "find_callers",
    "find_callees",
    "trace_variable",
    "slice_on",
    "resolve_copybook",
    "get_data_layout",
    "grep",
    "run_cobol",
    "search_regulations",
]

SYSTEM_PROMPT = """\
Investigate whether COBOL behavior matches the cited regulation.
The code is not included in this prompt: acquire it through the supplied
ToolLayer tools such as read_program, read_paragraph, slice_on, trace_variable,
or grep. Tool signatures are: read_paragraph(program, name);
read_program(program); find_callers(program, para);
find_callees(program, para); trace_variable(var, program?);
slice_on(var, program?); resolve_copybook(name); get_data_layout(record);
grep(pattern); run_cobol(snippet, inputs?); search_regulations(query).
Call one tool per turn and keep observations bounded. Return exactly one JSON
object and stop. A tool object is the entire turn: never append an abstention,
finding, alternative, or corrected object after it. A proposed finding must
include a complete DriftPrediction and a separate claim, plus concrete
execution/static evidence hooks when available. The runtime will verify every
proposed finding; if evidence is insufficient, abstain.
read_program returns a paragraph index, not statement text. Follow it with
read_paragraph for a relevant paragraph before concluding that source evidence
is unavailable. If an observation is insufficient and another listed bounded
tool can obtain the needed evidence, call that tool; abstain only after the
relevant available evidence paths have been attempted.
"""

HYDE_SYSTEM_PROMPT = """\
Describe the regulatory obligation implemented by the supplied code-oriented
query. Use one natural-language sentence. Preserve the regulated entity,
action, threshold, comparator, time unit, and triggering event. Remove COBOL
identifiers and control-flow syntax. Do not cite or infer a clause identifier.
"""


def build_hyde_prompt(query: str) -> str:
    """Return the versioned T3.3b slice-to-description prompt."""

    return (
        f"{HYDE_SYSTEM_PROMPT}\n"
        "Code-oriented query:\n"
        f"{query.strip()}\n"
        "Regulatory rule description:"
    )


HUNT_PROMPTS: dict[str, str] = {
    "D1_stale_threshold": (
        "Hunt D1 stale values: compare the literal at each typed locus with "
        "the clause's resolved current-value leaf, including scalar, list, "
        "or enum-valued leaves; resolve composite target_path."
    ),
    "D2_missing_rule": (
        "Hunt D2 missing rules: establish absence across the scoped grep, "
        "caller graph, callee graph, and data slice; emit only when all four "
        "negative observations are present, and report typed insertion points."
    ),
    "D3_contradictory": (
        "Hunt D3 contradictions: obtain at least two typed loci that produce "
        "conflicting outcomes for the same regulated condition."
    ),
    "D4_stale_reference_data": (
        "Hunt D4 stale reference data only when the clause current value is "
        "itself an enum_set reference collection: compare the hardcoded "
        "enumeration and name missing or extra entries. A composite clause's "
        "enum-valued business-rule leaf remains D1."
    ),
    "D5_boundary_error": (
        "Hunt D5 boundary errors: compare the source comparator with the "
        "typed comparator at the resolved current-value leaf."
    ),
    "D6_dead_code": (
        "Hunt D6 dead compliance code: propose a dead_paragraph static claim "
        "for the existing verifier; do not infer deadness from caller absence."
    ),
    "D7_conformant": (
        "Hunt D7 conformance: require positive code evidence that the check "
        "exists and matches; absence is never a conformant default."
    ),
}


def build_hunt_prompt(
    drift_type: str,
    clause: RegulationClause,
    program_scope: str | None = None,
) -> str:
    """Build one deterministic per-class investigation question."""
    try:
        policy = HUNT_PROMPTS[drift_type]
    except KeyError:
        raise KeyError(f"no prompt template registered for {drift_type!r}") from None
    scope = program_scope or "the available corpus"
    return (
        f"{policy}\nScope: {scope}.\n"
        f"Clause: {clause.doc} {clause.clause_id} "
        f"(version {clause.version}, effective {clause.effective_date}): "
        f"{clause.text}"
    )


class AgentResponse(BaseModel):
    """One cached or live model turn.

    ``token_count`` is the provider-reported turn-token usage and is part of
    the enforced run budget.  Keeping the complete response in the trajectory
    makes replay independent of another model call.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool", "finding", "abstain"]
    thought: str = Field(min_length=1)
    tool: ToolName | None = None
    arguments: dict[str, Any] = {}
    prediction: DriftPrediction | None = None
    claim: str | None = None
    exec_probe: ExecProbe | None = None
    static_claim: StaticClaim | None = None
    abstention_reason: str | None = None
    final_answer: str | None = None
    token_count: int = Field(ge=0)
    # Provider adapters populate these after parsing. They are deliberately
    # excluded from the provider-facing JSON schema so the model cannot spoof
    # contract telemetry.
    raw_provider_text: str | None = None
    contract_error: str | None = None

    @model_validator(mode="after")
    def _kind_shape(self) -> AgentResponse:
        if self.contract_error is not None and self.kind != "abstain":
            raise ValueError("a contract_error must fail closed as abstention")
        if self.kind == "tool":
            if self.tool is None:
                raise ValueError("a tool response requires tool")
            if self.prediction is not None or self.abstention_reason is not None:
                raise ValueError("a tool response cannot carry a finding/abstention")
        elif self.kind == "finding":
            if self.prediction is None or not self.claim:
                raise ValueError("a finding response requires prediction and claim")
            if self.tool is not None or self.abstention_reason is not None:
                raise ValueError("a finding response cannot carry a tool/abstention")
            if not self.final_answer:
                raise ValueError("a finding response requires final_answer")
        else:
            if not self.abstention_reason:
                raise ValueError("an abstain response requires abstention_reason")
            if self.tool is not None or self.prediction is not None:
                raise ValueError("an abstain response cannot carry a tool/finding")
        return self


def respond_with_contract_repair(
    model: DecisionModel,
    *,
    system_prompt: str,
    question: str,
    transcript: list[dict[str, Any]],
    max_repairs: int = 1,
    repair_allowed: Callable[[AgentResponse], bool] | None = None,
) -> tuple[AgentResponse, list[AgentResponse]]:
    """Call a provider and allow one provider-neutral contract repair.

    Every attempt is returned for trajectory and rejection-rate accounting.
    Semantic abstentions are final responses, not repair triggers.
    """

    response = model.respond(
        system_prompt=system_prompt,
        question=question,
        transcript=transcript,
    )
    attempts = [response]
    if (
        response.contract_error is None
        or max_repairs <= 0
        or (repair_allowed is not None and not repair_allowed(response))
    ):
        return response, attempts

    repair_question = (
        f"{question}\n\n"
        "CONTRACT REPAIR (one attempt only): your previous response did not "
        "satisfy the response contract. Return a complete replacement JSON "
        "object. Do not discuss the error.\n"
        f"Typed contract error: {response.contract_error}\n"
        "Previous raw response:\n"
        f"{response.raw_provider_text or '<empty>'}"
    )
    repaired = model.respond(
        system_prompt=system_prompt,
        question=repair_question,
        transcript=transcript,
    )
    attempts.append(repaired)
    return repaired, attempts


class DecisionModel(Protocol):
    """Provider-neutral next-action seam consumed by InvestigationLoop."""

    model_id: str
    temperature: float
    seed: int | None

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse: ...


class CachedDecisionModel:
    """Deterministic offline model backed by a committed JSON response list."""

    # DECISION (provider seam): cache replay implements the same tiny protocol
    # as a live provider adapter; the loop never imports an SDK or opens a cache.
    def __init__(
        self,
        cache_path: Path,
        *,
        cache_key: str | None = None,
        model_id: str = MODEL_ID,
        temperature: float = MODEL_TEMPERATURE,
        seed: int | None = MODEL_SEED,
    ) -> None:
        if temperature != 0:
            raise ValueError("T3.5 deterministic cache requires temperature=0")
        self.cache_path = Path(cache_path)
        self.model_id = model_id
        self.temperature = temperature
        self.seed = seed
        raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        if cache_key is not None:
            if not isinstance(raw, dict) or cache_key not in raw:
                raise KeyError(
                    f"cached response key {cache_key!r} missing from {self.cache_path}"
                )
            raw = raw[cache_key]
        if not isinstance(raw, list):
            raise TypeError("cached model responses must be a JSON list")
        self._responses = [
            AgentResponse.model_validate(_migrate_cached_prediction(row))
            for row in raw
        ]
        self._cursor = 0

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse:
        del system_prompt, question, transcript
        if self._cursor >= len(self._responses):
            raise RuntimeError(
                f"cached decision model exhausted after {self._cursor} responses"
            )
        response = self._responses[self._cursor]
        self._cursor += 1
        # Return a copy so a caller cannot mutate the committed replay sequence.
        return response.model_copy(deep=True)


def _migrate_cached_prediction(row: Any) -> Any:
    """Read legacy v2 response fixtures without widening the live contract."""

    if not isinstance(row, dict):
        return row
    migrated = dict(row)
    prediction = migrated.get("prediction")
    if isinstance(prediction, dict):
        prediction = dict(prediction)
        prediction.pop("provenance", None)
        if "rationale" not in prediction and "gold_rationale" in prediction:
            prediction["rationale"] = prediction.pop("gold_rationale")
        migrated["prediction"] = prediction
    return migrated
