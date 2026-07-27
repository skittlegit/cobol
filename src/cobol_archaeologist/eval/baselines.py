"""Gold-hidden context construction for the two mandatory M4 baselines."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.schemas import DriftInstance, RegulationClause
from cobol_archaeologist.tool_types import RegSearchHit, Slice, ToolLayer


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
