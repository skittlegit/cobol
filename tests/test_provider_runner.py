"""T5.3 Amendment 1: the extended Phase-5 provider-runner identities.

Offline only — nothing here contacts a provider. These gates cover the runner
contract for `plain_llm`, `rag_dense`, and `rag_reranker`: prompt construction,
envelope validation, clause binding, the mode pinning that makes a mislabeled
RAG artifact impossible, and the shared non-agent budget.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cobol_archaeologist.eval.baselines import (
    RAG_CONTEXT_TYPES,
    RAG_RETRIEVAL_MODES,
    OracleSliceContext,
    PlainLLMContext,
    RAGDenseContext,
    RAGRerankerContext,
    rag_baseline_context,
)
from cobol_archaeologist.eval.codex_batch import (
    CodexBaselineEnvelope,
    SubmittedResponse,
    validate_baseline_envelope,
)
from cobol_archaeologist.eval.codex_live import (
    batch_size_for,
    build_baseline_prompt,
    select_baseline_clause,
)
from cobol_archaeologist.eval.live import (
    AGENT_BUDGET,
    BASELINE_BUDGET,
    BASELINE_SYSTEM_IDS,
    SYSTEM_IDS,
    baseline_question,
)
from cobol_archaeologist.schemas import RegulationClause

RAG_SYSTEMS = ("rag_dense", "rag_reranker")
NEW_SYSTEMS = ("plain_llm", *RAG_SYSTEMS)


def _clause(text: str = "The issuer must act within seven days.") -> RegulationClause:
    return RegulationClause(
        doc="RBI-Test",
        clause_id="1",
        version="2026-01-01",
        effective_date="2026-01-01",
        text=text,
        current_value=None,
    )


def _hit(clause: RegulationClause, score: float = 1.0) -> dict:
    return {"clause": clause.model_dump(mode="json"), "score": score}


def _context(system_id: str, clause: RegulationClause, *, hits: int = 2):
    if system_id == "plain_llm":
        return PlainLLMContext(clause=clause, program="PROGRAM SOURCE")
    if system_id == "oracle_slice":
        return OracleSliceContext(clause=clause, program="PROGRAM SOURCE", slices=[])
    return RAG_CONTEXT_TYPES[system_id].model_validate(
        {
            "clause_query": clause.text,
            "retrieved_clauses": [_hit(clause) for _ in range(hits)],
            "program": "PROGRAM SOURCE",
        }
    )


def _abstention() -> SubmittedResponse:
    return SubmittedResponse(
        kind="abstain",
        thought="The available evidence does not support a finding.",
        prediction=None,
        claim=None,
        exec_probe=None,
        static_claim=None,
        abstention_reason="insufficient evidence",
        final_answer="Abstained: insufficient evidence",
    )


def _finding() -> SubmittedResponse:
    return SubmittedResponse(
        kind="finding",
        thought="The coded window exceeds the mandated one.",
        prediction={
            "code_locus": {
                "loci": [
                    {
                        "program": "CBACT04C",
                        "file": "CBACT04C.cbl",
                        "line_span": (10, 10),
                    }
                ],
                "slice_vars": ["WS-DAYS"],
                "is_interprocedural": False,
            },
            "drift_type": "D1_stale_threshold",
            "target_path": None,
            "labels": {
                "program_level": "drift",
                "paragraph_level": "drift",
                "line_level": [],
            },
            "rationale": "Source uses 30 days where the clause mandates seven.",
        },
        claim="The issuer must act within seven days.",
        exec_probe=None,
        static_claim=None,
        abstention_reason=None,
        final_answer="Drift: the coded window is 30 days.",
    )


def _envelope(clause_index: int | None, response: SubmittedResponse):
    return CodexBaselineEnvelope(
        results=[
            {
                "alias": "drift_900000",
                "clause_index": clause_index,
                "response": response,
            }
        ]
    )


def test_registry_carries_the_amendment_1_identities():
    assert SYSTEM_IDS == (
        "agent",
        "plain_llm",
        "rag_dense",
        "rag_reranker",
        "oracle_slice",
    )
    assert "dense_rag" not in SYSTEM_IDS
    assert BASELINE_SYSTEM_IDS == (
        "plain_llm",
        "rag_dense",
        "rag_reranker",
        "oracle_slice",
    )


@pytest.mark.parametrize("system_id", NEW_SYSTEMS)
def test_new_system_round_trips_prompt_and_envelope(system_id: str):
    """Each new identity survives prompt build, envelope validation, binding."""

    clause = _clause()
    context = _context(system_id, clause)
    prompt = build_baseline_prompt(
        system_id,
        [{"alias": "drift_900000", "context": context.model_dump(mode="json")}],
    )
    assert system_id in prompt
    assert "Tools and file access are not" in prompt

    clause_index = 0 if system_id in RAG_RETRIEVAL_MODES else None
    envelope = _envelope(clause_index, _finding())
    assert (
        validate_baseline_envelope(
            envelope,
            ["drift_900000"],
            system_id=system_id,
            retrieved_counts={"drift_900000": 2},
        )
        == []
    )
    assert select_baseline_clause(system_id, clause_index, context) == clause
    assert baseline_question(system_id, context)


def test_plain_llm_prompt_offers_no_retrieval_and_binds_its_only_clause():
    clause = _clause()
    context = _context("plain_llm", clause)
    prompt = build_baseline_prompt(
        "plain_llm",
        [{"alias": "drift_900000", "context": context.model_dump(mode="json")}],
    )

    assert "Set clause_index to null" in prompt
    assert "retrieved_clauses" not in prompt
    assert not hasattr(context, "retrieved_clauses")
    assert select_baseline_clause("plain_llm", None, context) == clause


@pytest.mark.parametrize("system_id", RAG_SYSTEMS)
def test_rag_prompt_exposes_its_retrieved_clause_list(system_id: str):
    context = _context(system_id, _clause())
    prompt = build_baseline_prompt(
        system_id,
        [{"alias": "drift_900000", "context": context.model_dump(mode="json")}],
    )

    assert "zero-based index" in prompt
    assert "context.retrieved_clauses" in prompt


def test_plain_llm_envelope_rejects_a_clause_index():
    envelope = _envelope(0, _finding())

    with pytest.raises(ValueError, match="must not carry a clause_index"):
        validate_baseline_envelope(
            envelope,
            ["drift_900000"],
            system_id="plain_llm",
        )
    # An abstention binds no clause, so the rule applies to findings only.
    assert (
        validate_baseline_envelope(
            _envelope(None, _abstention()),
            ["drift_900000"],
            system_id="plain_llm",
        )
        == []
    )


@pytest.mark.parametrize("system_id", RAG_SYSTEMS)
@pytest.mark.parametrize("clause_index", [None, 2, 7, -1])
def test_rag_envelope_rejects_missing_or_out_of_range_clause_index(
    system_id: str,
    clause_index: int | None,
):
    envelope = _envelope(clause_index, _finding())
    expected = "requires a clause_index" if clause_index is None else "is outside"

    with pytest.raises(ValueError, match=expected):
        validate_baseline_envelope(
            envelope,
            ["drift_900000"],
            system_id=system_id,
            retrieved_counts={"drift_900000": 2},
        )


@pytest.mark.parametrize("system_id", RAG_SYSTEMS)
def test_rag_envelope_requires_the_retrieved_count_to_bound_against(system_id: str):
    with pytest.raises(ValueError, match="requires the retrieved_clauses count"):
        validate_baseline_envelope(
            _envelope(0, _finding()),
            ["drift_900000"],
            system_id=system_id,
        )


def test_retired_runner_identity_is_rejected_everywhere():
    with pytest.raises(ValueError, match="baseline prompt requires"):
        build_baseline_prompt("dense_rag", [{"alias": "drift_900000", "context": {}}])
    with pytest.raises(ValueError, match="unsupported baseline system"):
        validate_baseline_envelope(
            _envelope(None, _abstention()),
            ["drift_900000"],
            system_id="dense_rag",
        )
    with pytest.raises(KeyError):
        batch_size_for("dense_rag")


def test_rag_context_aliases_pin_retrieval_mode_by_construction():
    assert RAGDenseContext.model_fields["retrieval_mode"].default == "dense"
    assert (
        RAGRerankerContext.model_fields["retrieval_mode"].default == "hybrid_rerank"
    )

    payload = {
        "clause_query": "seven days",
        "retrieved_clauses": [],
        "program": "PROGRAM SOURCE",
    }
    assert RAGDenseContext.model_validate(payload).retrieval_mode == "dense"
    assert (
        RAGRerankerContext.model_validate(payload).retrieval_mode == "hybrid_rerank"
    )

    with pytest.raises(ValidationError):
        RAGDenseContext(retrieval_mode="hybrid_rerank", **payload)
    with pytest.raises(ValidationError):
        RAGRerankerContext(retrieval_mode="dense", **payload)


class _FakeSearch:
    """Stand-in for RegulationSearch; no index, no model, no network."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.queries: list[str] = []

    def search(self, query: str, k: int = 5):
        self.queries.append(query)
        return []


@pytest.mark.parametrize("system_id", RAG_SYSTEMS)
def test_rag_baseline_context_delegates_and_refuses_a_mismatched_mode(system_id: str):
    expected_mode = RAG_RETRIEVAL_MODES[system_id]
    search = _FakeSearch(expected_mode)

    context = rag_baseline_context(
        system_id,
        "seven days",
        program="PROGRAM SOURCE",
        search=search,
    )
    assert isinstance(context, RAG_CONTEXT_TYPES[system_id])
    assert context.retrieval_mode == expected_mode
    # Delegated to retrieved_rag_context rather than re-implementing retrieval.
    assert search.queries == ["seven days"]

    other = "hybrid_rerank" if expected_mode == "dense" else "dense"
    with pytest.raises(ValueError, match=f"requires retrieval_mode={expected_mode!r}"):
        rag_baseline_context(
            system_id,
            "seven days",
            program="PROGRAM SOURCE",
            search=_FakeSearch(other),
        )


def test_baseline_budget_is_shared_across_the_four_non_agent_systems():
    assert set(BASELINE_SYSTEM_IDS) == {
        "plain_llm",
        "rag_dense",
        "rag_reranker",
        "oracle_slice",
    }
    budgets = {system_id: BASELINE_BUDGET for system_id in BASELINE_SYSTEM_IDS}
    assert len({id(budget) for budget in budgets.values()}) == 1
    for system_id in BASELINE_SYSTEM_IDS:
        assert budgets[system_id] == BASELINE_BUDGET
        assert budgets[system_id].max_tool_calls == 0
    assert BASELINE_BUDGET != AGENT_BUDGET
