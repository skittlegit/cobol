"""T3.3b gates: offline HyDE transformation and raw-query comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cobol_archaeologist.rag.hyde import (
    CACHE_SCHEMA_VERSION,
    DEFAULT_CACHE,
    HYDE_PROMPT_VERSION,
    CachedHyDEGenerator,
    HeuristicHyDEGenerator,
    compare_raw_and_hyde,
    load_hyde_cache,
)
from cobol_archaeologist.rag.index import (
    MODES,
    RegulationIndex,
    load_corpus,
    resolve_gold_queries,
)
from cobol_archaeologist.rag.search import RegulationSearch

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "tests" / "fixtures" / "retrieval" / "queries.jsonl"


def _raw_queries() -> list[dict]:
    return [
        json.loads(line)
        for line in QUERIES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_cache_covers_fixed_queries_without_gold_fields():
    cache = load_hyde_cache(DEFAULT_CACHE)
    raw = _raw_queries()

    assert cache.schema_version == CACHE_SCHEMA_VERSION
    assert cache.provenance.prompt_version == HYDE_PROMPT_VERSION
    assert cache.provenance.provider == "OpenAI"
    assert len(cache.records) == len(raw) == 24
    assert {record.query_id for record in cache.records} == {
        row["query_id"] for row in raw
    }
    assert {record.raw_query for record in cache.records} == {
        row["query"] for row in raw
    }
    serialized = cache.model_dump_json()
    assert "record_id" not in serialized
    assert "gold_doc" not in serialized
    assert "gold_clause" not in serialized


def test_cached_generation_is_offline_deterministic_and_q23_is_specific():
    generator = CachedHyDEGenerator(DEFAULT_CACHE)
    q23 = next(row for row in _raw_queries() if row["query_id"] == "q23")

    first = generator.describe(q23["query"])
    second = generator.describe(q23["query"])

    assert first == second
    assert "central kyc records registry" in first.lower()
    assert "customer information" in first.lower()
    assert "account closure" not in first.lower()


def test_unseen_query_has_deterministic_local_fallback():
    generator = CachedHyDEGenerator(
        DEFAULT_CACHE,
        fallback=HeuristicHyDEGenerator(),
    )
    raw = "IF WS-DAYS-PAST-DUE > 3 MOVE 'Y' TO WS-REPORT-CIC"

    transformed = generator.describe(raw)

    assert transformed == generator.describe(raw)
    assert "days past due" in transformed.lower()
    assert "report credit information company" in transformed.lower()
    assert "ws-" not in transformed.lower()


def test_regulation_search_applies_hyde_before_index_search(monkeypatch):
    search = RegulationSearch(
        mode="bm25",
        use_hyde=True,
        hyde_generator=HeuristicHyDEGenerator(),
    )
    seen: list[str] = []
    original = search._index.search

    def capture(query, *args, **kwargs):
        seen.append(query)
        return original(query, *args, **kwargs)

    monkeypatch.setattr(search._index, "search", capture)
    search.search("IF WS-DAYS-PAST-DUE > 3 MOVE 'Y' TO WS-REPORT-CIC")

    assert seen
    assert "ws-" not in seen[0].lower()
    assert "days past due" in seen[0].lower()


@pytest.mark.network
def test_hyde_strictly_improves_dense_and_hybrid_rerank():
    pytest.importorskip("sentence_transformers")
    from cobol_archaeologist.rag.embed import DenseEmbedder, Reranker

    index = RegulationIndex.build(
        load_corpus(),
        embedder=DenseEmbedder(),
        reranker=Reranker(),
    )
    result = compare_raw_and_hyde(
        index,
        resolve_gold_queries(),
        CachedHyDEGenerator(DEFAULT_CACHE),
    )

    assert set(result["raw"]["metrics"]) == set(MODES)
    assert set(result["hyde"]["metrics"]) == set(MODES)
    assert result["hyde"]["metrics"]["dense"]["mrr@5"] > result["raw"]["metrics"][
        "dense"
    ]["mrr@5"]
    assert result["hyde"]["metrics"]["hybrid_rerank"]["mrr@5"] > result["raw"][
        "metrics"
    ]["hybrid_rerank"]["mrr@5"]
    assert any(
        result["hyde"]["metrics"][mode]["mrr@5"]
        > result["raw"]["metrics"][mode]["mrr@5"]
        for mode in MODES
    )

    q23 = next(row for row in result["per_query"] if row["query_id"] == "q23")
    assert q23["hyde"]["hybrid_rerank"] is not None
