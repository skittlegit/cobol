"""The comparison baseline: single-shot RAG with hybrid retrieval and reranking.

The baseline sees the retrieved regulation clauses and a bounded,
query-relevant window of the program source.  It has no tools.  Its answer
passes the same verifier as the detector before it counts.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.agent.policy import confidence_for_tier
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
from cobol_archaeologist.eval.detector import SubmittedResponse, bind_response
from cobol_archaeologist.eval.materialize import MaterializedSource
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.verify import Entailer, Finding, verify
from cobol_archaeologist.rag.index import tokenize
from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.schemas import DriftInstance, RegulationClause
from cobol_archaeologist.tool_types import RegSearchHit, ToolLayer

SYSTEM_ID = "rag_reranker"
BATCH_SIZE = 5
BASELINE_BUDGET = BudgetSpec(
    max_steps=1,
    max_tool_calls=0,
    max_tokens=2_000_000,
    wall_clock_timeout_s=1_800,
)
ALIAS_PATTERN = r"^drift_9\d{5}$"


class RAGContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_mode: Literal["hybrid_rerank"] = "hybrid_rerank"
    clause_query: str
    retrieved_clauses: list[RegSearchHit]
    program: str


class SubmittedBaselineCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(pattern=ALIAS_PATTERN)
    clause_index: int | None
    response: SubmittedResponse


class BaselineEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SubmittedBaselineCase] = Field(min_length=1, max_length=BATCH_SIZE)


def _line_windows(
    files: dict[str, str], query: str, *, window_lines: int = 20
) -> list[tuple[int, str, int, list[str]]]:
    query_tokens = set(tokenize(query))
    windows: list[tuple[int, str, int, list[str]]] = []
    stride = max(1, window_lines // 2)
    for filename, text in sorted(files.items()):
        lines = text.splitlines()
        for start in range(0, max(1, len(lines)), stride):
            chunk = lines[start : start + window_lines]
            if not chunk:
                continue
            score = len(query_tokens & set(tokenize("\n".join(chunk))))
            windows.append((score, filename, start, chunk))
            if start + window_lines >= len(lines):
                break
    return sorted(windows, key=lambda row: (-row[0], row[1], row[2]))


def bounded_code_context(
    source: MaterializedSource, query: str, *, max_lines: int = 200
) -> str:
    """Select label-free query-relevant code windows under a hard line cap."""

    selected: list[tuple[str, int, list[str]]] = []
    covered: dict[str, set[int]] = {}
    used = 0
    for _score, filename, start, lines in _line_windows(source.files, query):
        indexes = set(range(start, start + len(lines)))
        if indexes & covered.setdefault(filename, set()):
            continue
        room = max_lines - used
        if room <= 0:
            break
        chunk = lines[:room]
        selected.append((filename, start, chunk))
        covered[filename].update(range(start, start + len(chunk)))
        used += len(chunk)
    rendered: list[str] = []
    for filename, start, lines in sorted(selected, key=lambda row: (row[0], row[1])):
        rendered.append(f"FILE {filename} LINES {start + 1}-{start + len(lines)}")
        rendered.extend(
            f"{number:04d}: {line}"
            for number, line in enumerate(lines, start=start + 1)
        )
    return "\n".join(rendered)


def build_context(
    row: DriftInstance, source: MaterializedSource, search: RegulationSearch
) -> RAGContext:
    if search.mode != "hybrid_rerank":
        raise ValueError("the baseline requires hybrid_rerank retrieval")
    query = row.regulation_clause.text
    return RAGContext(
        clause_query=query,
        retrieved_clauses=search.search(query),
        program=bounded_code_context(source, query),
    )


def build_prompt(cases: Sequence[dict]) -> str:
    visible = json.dumps(list(cases), ensure_ascii=False, separators=(",", ":"))
    return f"""\
Perform one evidence-grounded COBOL compliance classification for each opaque
case using only its supplied retrieval context. Tools and file access are not
available. Return exactly one response per alias under the required JSON
schema. For a finding, set clause_index to the zero-based index of the
supporting clause in context.retrieved_clauses; the host attaches that clause
and the case identity. Author the remaining prediction fields, cite concrete
source loci from the context, and include verifier hooks. The separate claim
is the citation hypothesis: write only a regulatory obligation entailed by the
selected clause, without COBOL identifiers or implementation facts. Put the
code-versus-clause comparison in prediction.rationale and final_answer. In a
locus, program names the containing executable program and file names the
physical copybook/source filename. Set target_path to null unless a D1 or D5
finding targets a composite current_value; then it must name a non-composite
leaf from the selected clause. For D7_conformant, set labels.program_level and
labels.paragraph_level to conformant and labels.line_level to an empty list.
For every other class, set labels.program_level to drift. D7 requires
positive source evidence of conformance and is never a default verdict. Abstain when evidence is
insufficient. Do not use or infer hidden labels, generation provenance,
mutation metadata, git history, file timestamps, formatting, comment
freshness, or identifier style.

Detector-visible cases:
{visible}
"""


def select_clause(clause_index: int | None, context: RAGContext) -> RegulationClause:
    if clause_index is None:
        raise ValueError("a baseline finding requires clause_index")
    if not 0 <= clause_index < len(context.retrieved_clauses):
        raise ValueError(
            f"clause_index {clause_index} is outside "
            f"{len(context.retrieved_clauses)} retrieved clauses"
        )
    return context.retrieved_clauses[clause_index].clause


def finalize_case(
    submitted: SubmittedBaselineCase,
    *,
    gold: DriftInstance,
    context: RAGContext,
    tools: ToolLayer,
    entailer: Entailer,
    source_sha256: str,
    run_key: str,
    token_count: int,
    model_id: str,
) -> EvaluationRecord:
    """Bind the answer to a visible clause and verify it before it counts."""

    binding_error = None
    clause = gold.regulation_clause
    if submitted.response.kind == "finding":
        try:
            clause = select_clause(submitted.clause_index, context)
        except ValueError as exc:
            binding_error = str(exc)
    response = bind_response(
        submitted.response,
        instance_id=gold.instance_id,
        clause=clause,
        token_count=token_count,
        prebinding_error=binding_error,
    )
    question = context.model_dump_json()
    verification = None
    prediction = None
    reason = response.abstention_reason
    if response.kind == "finding":
        finding = Finding.from_prediction(
            response.prediction, claim=response.claim
        ).model_copy(
            update={
                "exec_probe": response.exec_probe,
                "static_claim": response.static_claim,
            }
        )
        try:
            verification = verify(finding, tools, entailer=entailer)
        except Exception as exc:  # noqa: BLE001
            reason = (
                "verification unavailable; refusing emission: "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            if verification.verified:
                prediction = response.prediction
            else:
                reason = verification.rejected_reason or "finding was not verified"
    reason = reason or "model abstained"
    abstained = prediction is None
    trajectory = Trajectory(
        question=question,
        steps=[],
        model_responses=[response],
        verification=verification,
        finding=prediction,
        abstained=abstained,
        abstention_reason=reason if abstained else None,
        budget=BASELINE_BUDGET,
        budget_exhausted=False,
        tokens_used=token_count,
        token_usage_recorded=True,
        contract_repairs=0,
        final_answer=response.final_answer
        or (f"Abstained: {reason}" if abstained else verification.evidence),
        model_id=model_id,
        seed=None,
    )
    return EvaluationRecord(
        instance_id=gold.instance_id,
        gold=gold,
        prediction=prediction,
        confidence=(
            confidence_for_tier(verification.tier) if prediction is not None else None
        ),
        verification=verification,
        trajectory=trajectory,
        abstained=abstained,
        abstention_reason=reason if abstained else None,
        system_id=SYSTEM_ID,
        source_sha256=source_sha256,
        run_key=run_key,
    )
