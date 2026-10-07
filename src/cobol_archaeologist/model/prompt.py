"""Shared detection vocabulary: tool names, class policy text, and responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.model.verify import ExecProbe, StaticClaim
from cobol_archaeologist.schemas import DriftPrediction, DriftType

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
`claim` is the clause-grounded regulatory proposition that the cited clause
entails. Restate the applicable regulated entity, action, trigger, threshold,
comparator, and unit in natural language. Never put a COBOL program,
paragraph, identifier, line, implementation fact, or drift diagnosis in
`claim`; those code facts belong in `prediction.rationale`, `static_claim`,
and `final_answer`. The most reliable claim is the clause's own sentence
that states the relevant obligation, copied verbatim; otherwise keep a close
paraphrase that preserves its distinctive regulated terms and adds no entity,
qualifier, or mechanism the clause does not state.
For a static evidence hook, copy `static_claim.literal` and
`static_claim.comparator` exactly from source text returned by a cited tool
observation. These fields contain source tokens, never a prose comparison;
put the explanation in prediction.rationale.
For D7 over a boolean-required behavior, choose a literal that directly
participates in the conformant operation (for example, the excluded amount in
the subtraction), not an unrelated nearby threshold or branch token.
For every predicted source locus, `file` is null when the line is in the
program's own source; it is never the program filename. Negative example
(own source): {"program": "CLOSPEN1", "file": null}. Positive example
(COPY expansion): {"program": "CLOSPEN2", "file": "WSDAYBAS.cpy"}.
read_program returns a paragraph index, not statement text. Follow it with
read_paragraph for a relevant paragraph before concluding that source evidence
is unavailable. If an observation is insufficient and another listed bounded
tool can obtain the needed evidence, call that tool; abstain only after the
relevant available evidence paths have been attempted.
"""

HUNT_PROMPTS: dict[str, str] = {
    "D1_stale_threshold": (
        "Hunt D1 stale values: compare the literal at each typed locus with "
        "the clause's resolved current-value leaf, including scalar, list, "
        "or enum-valued leaves; resolve composite target_path. A resolved "
        "current_value is required for D1."
    ),
    "D2_missing_rule": (
        "Hunt D2 missing rules or required outcomes: inspect the relevant "
        "paragraph, scoped grep, and data slice, and show that the specific "
        "required behavior or violation branch is absent. Positive surrounding "
        "control flow does not prove that the required outcome exists. Report "
        "typed insertion points. Reserve D2 for absence without an existing "
        "source state or action that positively conflicts with the requirement. "
        "The clause current_value may be null for D2."
    ),
    "D3_contradictory": (
        "Hunt D3 contradictions: identify source behavior that positively "
        "contradicts the regulated condition. Use multiple typed loci when the "
        "contradiction is internal, but one typed source locus may contradict "
        "the trusted clause directly. If validation detects a violation and "
        "sets a denial or invalid state but a reachable downstream action "
        "ignores or bypasses that state, classify the conflicting implemented "
        "behavior as D3 rather than D2."
    ),
    "D4_stale_reference_data": (
        "Hunt D4 stale reference data only when the clause current value is "
        "itself an enum_set reference collection: compare the hardcoded "
        "enumeration and name missing or extra entries. A composite clause's "
        "enum-valued business-rule leaf remains D1. A resolved current_value "
        "is required for D4."
    ),
    "D5_boundary_error": (
        "Hunt D5 boundary errors: evaluate the source comparator together with "
        "the branch action and say whether the transition occurs early or late. "
        "A resolved current_value is required for D5."
    ),
    "D6_dead_code": (
        "Hunt D6 dead or disabled compliance code: use dead_paragraph for an "
        "unreachable paragraph, or an exact literal hook for a reachable "
        "compliance branch disabled by an always-false/default-off guard. "
        "Do not infer deadness from caller absence alone. "
        "The clause current_value may be null for D6."
    ),
    "D7_conformant": (
        "Hunt D7 conformance: require positive code evidence that the check "
        "exists and matches; absence is never a conformant default. The clause "
        "current_value may be null for D7."
    ),
}


class EvidenceLedgerNote(BaseModel):
    """Model-authored claim tied to one exact, case-local observation."""

    model_config = ConfigDict(extra="forbid")

    observation_step: int = Field(ge=1)
    observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hypothesis: DriftType
    bearing: Literal["supports", "refutes", "context"]
    rationale: str = Field(min_length=1)


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
    claim: str | None = Field(
        default=None,
        description=(
            "Clause-grounded regulatory proposition entailed by the cited "
            "clause; code and drift facts belong in prediction.rationale."
        ),
    )
    exec_probe: ExecProbe | None = None
    static_claim: StaticClaim | None = None
    abstention_reason: str | None = None
    final_answer: str | None = None
    token_count: int = Field(ge=0)
    token_count_recorded: bool = True
    # Provider adapters populate these after parsing. They are deliberately
    # excluded from the provider-facing JSON schema so the model cannot spoof
    # contract telemetry.
    raw_provider_text: str | None = None
    contract_error: str | None = None
    evidence_ledger: list[EvidenceLedgerNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _kind_shape(self) -> AgentResponse:
        if not self.token_count_recorded and self.token_count != 0:
            raise ValueError("unrecorded token usage must use the zero placeholder")
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
