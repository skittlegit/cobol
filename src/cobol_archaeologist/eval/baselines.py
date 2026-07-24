"""Gold-hidden context construction for the two mandatory M4 baselines."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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
