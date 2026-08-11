"""Gold-hidden context construction for the M4 and Phase-5 baselines."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.schemas import DriftInstance, RegulationClause
from cobol_archaeologist.tool_types import RegSearchHit, Slice, ToolLayer


# DECISION (T5.3 Amendment 1): `DenseRAGContext` and `dense_rag_context` are
# retained, unused by the Phase-5 runner IDs, as the historical shape of the M4
# `dense_rag` artifact. T5.4 reuse has to read those committed contexts back,
# and the relabel to `rag_reranker` is deferred behind the
# `search.mode == "hybrid_rerank"` identity check. Deleting them here would
# strand that reuse path; new runs must use `RetrievedRAGContext` instead.
class DenseRAGContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_query: str
    retrieved_clauses: list[RegSearchHit]
    program: str


class OracleSliceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause: RegulationClause
    program: str
    slices: list[Slice]


class PlainLLMContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause: RegulationClause
    program: str


class RetrievedRAGContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_mode: Literal["dense", "hybrid_rerank"]
    clause_query: str
    retrieved_clauses: list[RegSearchHit]
    program: str


class RAGDenseContext(RetrievedRAGContext):
    """`RetrievedRAGContext` pinned to explicit dense retrieval."""

    retrieval_mode: Literal["dense"] = "dense"


class RAGRerankerContext(RetrievedRAGContext):
    """`RetrievedRAGContext` pinned to hybrid retrieval plus cross-encoder."""

    retrieval_mode: Literal["hybrid_rerank"] = "hybrid_rerank"


RAG_RETRIEVAL_MODES: dict[str, str] = {
    "rag_dense": "dense",
    "rag_reranker": "hybrid_rerank",
}
RAG_CONTEXT_TYPES: dict[str, type[RetrievedRAGContext]] = {
    "rag_dense": RAGDenseContext,
    "rag_reranker": RAGRerankerContext,
}
# Baselines whose context exposes exactly one clause, so a finding has no index
# to select and must leave `clause_index` null.
SINGLE_CLAUSE_BASELINES: frozenset[str] = frozenset({"plain_llm", "oracle_slice"})


def dense_rag_context(
    clause_query: str,
    *,
    program: str,
    tools: ToolLayer,
) -> DenseRAGContext:
    return DenseRAGContext(
        clause_query=clause_query,
        retrieved_clauses=tools.search_regulations(clause_query),
        program=program,
    )


def oracle_slice_context(
    gold: DriftInstance,
    *,
    tools: ToolLayer,
) -> OracleSliceContext:
    """Use gold slice-variable names only; no labels, class, or rationale."""

    program = gold.provenance.base_program.rsplit(".", 1)[0]
    return OracleSliceContext(
        clause=gold.regulation_clause,
        program=program,
        slices=[
            tools.slice_on(variable, program=program)
            for variable in gold.code_locus.slice_vars
        ],
    )


def plain_llm_context(
    clause: RegulationClause,
    *,
    program: str,
) -> PlainLLMContext:
    return PlainLLMContext(clause=clause, program=program)


def retrieved_rag_context(
    clause_query: str,
    *,
    program: str,
    search: RegulationSearch,
) -> RetrievedRAGContext:
    if search.mode not in {"dense", "hybrid_rerank"}:
        raise ValueError("Phase-5 RAG baseline requires dense or hybrid_rerank mode")
    return RetrievedRAGContext(
        retrieval_mode=search.mode,
        clause_query=clause_query,
        retrieved_clauses=search.search(clause_query),
        program=program,
    )


def rag_baseline_context(
    system_id: str,
    clause_query: str,
    *,
    program: str,
    search: RegulationSearch,
) -> RetrievedRAGContext:
    """Build the mode-pinned RAG context for one Phase-5 runner ID.

    Delegates retrieval to :func:`retrieved_rag_context` rather than repeating
    it, then narrows the result to the alias whose ``retrieval_mode`` is pinned.
    A search configured in the wrong mode raises here, so a mislabeled artifact
    is impossible to produce rather than merely detectable afterwards.
    """

    expected = RAG_RETRIEVAL_MODES.get(system_id)
    if expected is None:
        raise ValueError(f"not a Phase-5 RAG baseline: {system_id!r}")
    if search.mode != expected:
        raise ValueError(
            f"{system_id} requires retrieval_mode={expected!r}, "
            f"got {search.mode!r}"
        )
    base = retrieved_rag_context(clause_query, program=program, search=search)
    return RAG_CONTEXT_TYPES[system_id].model_validate(base.model_dump())
