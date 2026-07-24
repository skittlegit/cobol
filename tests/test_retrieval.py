"""T3.2 gates — hybrid retrieval + reranker.

Split per the work order's review-environment constraint:

- Offline default set (review chat re-runs these): BM25 correctness on a tiny
  synthetic corpus, RRF fusion math, the gold-resolution join (24/24 queries
  resolve against clauses.jsonl), the ``doc`` filter, and index-build
  determinism.
- ``@pytest.mark.network``: anything that loads the pinned model weights
  (dense / hybrid / hybrid_rerank and the relevance bar). Run locally before push.

The retrieval corpus is the frozen chunker output at
``tests/fixtures/retrieval/chunks.jsonl`` (regenerate per that dir's README).
"""

import pytest

from cobol_archaeologist.rag.index import (
    BM25,
    MODES,
    RegulationIndex,
    _write_relevance_report,
    build_relevance_report,
    evaluate_modes,
    load_corpus,
    reciprocal_rank_fusion,
    resolve_gold_queries,
    tokenize,
)
from cobol_archaeologist.rag.schemas import RegulationChunk


@pytest.fixture(scope="module")
def corpus() -> list[RegulationChunk]:
    return load_corpus()


# --- Gate A (offline) ----------------------------------------------------------


def test_tokenizer_splits_cobol_identifiers():
    toks = tokenize("IF WS-DAYS-SINCE-ISSUE > 30")
    assert "day" in toks and "issue" in toks and "30" in toks


def test_bm25_ranks_the_matching_doc_first():
    corpus = [
        "closure request penalty of five hundred rupees per day",
        "interest is levied only on the outstanding amount",
        "beneficial owner threshold for a partnership firm",
    ]
    bm25 = BM25().fit(corpus)
    scores = bm25.scores("penalty per day for closure", list(range(len(corpus))))
    assert scores[0] == max(scores) and scores[0] > 0.0
    # a query term absent everywhere contributes nothing
    assert bm25.scores("xylophone", [0, 1, 2]) == [0.0, 0.0, 0.0]


def test_rrf_rewards_agreement_across_rankings():
    # 3 is top of both lists -> must win; ties broken by id for determinism.
    # RRF now returns (index, score) pairs, ranked desc.
    ids = ["a", "b", "c", "d"]
    fused = reciprocal_rank_fusion([[2, 0, 1], [2, 1, 0]], ids, k=60)
    assert fused[0][0] == 2
    # Every fused entry carries a positive RRF score (F8: never all-zero).
    assert all(score > 0.0 for _, score in fused)
    assert fused[0][1] == max(score for _, score in fused)


def test_all_24_queries_resolve_to_gold(corpus):
    queries = resolve_gold_queries()
    assert len(queries) >= 20
    keyset = {(c.doc, c.clause_id) for c in corpus}
    for gq in queries:
        assert (gq.gold_doc, gq.gold_clause_id) in keyset, gq.query_id


def test_bm25_mode_needs_no_model(corpus):
    index = RegulationIndex.build(corpus)  # no embedder / reranker
    hits = index.search("closure penalty of Rs 500 per day", k=5, mode="bm25")
    assert len(hits) == 5


def test_doc_filter_restricts_to_one_document(corpus):
    doc = "RBI-KYC-Directions-2025"
    index = RegulationIndex.build(corpus)
    hits = index.search(
        "beneficial owner partnership threshold", k=5, doc=doc, mode="bm25"
    )
    assert hits and all(h.chunk.doc == doc for h in hits)


def test_dense_modes_raise_without_a_model(corpus):
    index = RegulationIndex.build(corpus)
    for mode in ("dense", "hybrid", "hybrid_rerank"):
        with pytest.raises(RuntimeError):
            index.search("any query", mode=mode)


def test_bm25_index_build_is_deterministic(corpus):
    q = "past due grace period before penal charges"
    a = [h.chunk.chunk_id for h in RegulationIndex.build(corpus).search(q, mode="bm25")]
    b = [h.chunk.chunk_id for h in RegulationIndex.build(corpus).search(q, mode="bm25")]
    assert a == b


# --- Gate B / C (network — loads pinned models) --------------------------------


@pytest.fixture(scope="module")
def model_index(corpus):
    st = pytest.importorskip("sentence_transformers")  # noqa: F841
    from cobol_archaeologist.rag.embed import DenseEmbedder, Reranker

    return RegulationIndex.build(corpus, embedder=DenseEmbedder(), reranker=Reranker())


@pytest.mark.network
def test_hybrid_rerank_beats_dense(corpus, model_index):
    queries = resolve_gold_queries()
    result = evaluate_modes(model_index, queries)
    dense = result["metrics"]["dense"]
    hyb = result["metrics"]["hybrid_rerank"]
    assert hyb["mrr@5"] > dense["mrr@5"]
    assert hyb["hit@1"] >= dense["hit@1"]
    assert hyb["hit@3"] >= dense["hit@3"]


@pytest.mark.network
def test_no_mode_returns_all_zero_scores(model_index):
    # F8: hybrid previously reported score 0.0 for every hit. No mode should
    # return an all-zero score vector for a query that has hits.
    q = "closure penalty of Rs 500 per day"
    for mode in MODES:
        hits = model_index.search(q, mode=mode)
        assert hits, mode
        assert any(h.score != 0.0 for h in hits), mode


@pytest.mark.network
def test_search_is_deterministic_across_builds(corpus, model_index):
    q = "activation OTP consent within 30 days of issuance"
    for mode in MODES:
        if mode in ("bm25",):
            continue
        a = [h.chunk.chunk_id for h in model_index.search(q, mode=mode)]
        b = [h.chunk.chunk_id for h in model_index.search(q, mode=mode)]
        assert a == b, mode


@pytest.mark.network
def test_build_relevance_report_writes_table(tmp_path):
    pytest.importorskip("sentence_transformers")  # loads pinned model weights
    out = tmp_path / "report.md"
    result = build_relevance_report(report_path=out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Mode comparison" in text and "hybrid_rerank" in text
    assert set(result["metrics"]) == set(MODES)


def test_relevance_report_replaces_only_canonical_generated_block(tmp_path):
    out = tmp_path / "T3.2-work-order.md"
    out.write_text(
        "# Work order\n\nkeep before\n"
        "<!-- BEGIN GENERATED RELEVANCE REPORT -->\nold evidence\n"
        "<!-- END GENERATED RELEVANCE REPORT -->\nkeep after\n",
        encoding="utf-8",
    )

    _write_relevance_report(out, ["## Relevance evidence", "", "new evidence"])

    text = out.read_text(encoding="utf-8")
    assert "keep before" in text and "keep after" in text
    assert "new evidence" in text and "old evidence" not in text
    assert text.count("<!-- BEGIN GENERATED RELEVANCE REPORT -->") == 1
    assert text.count("<!-- END GENERATED RELEVANCE REPORT -->") == 1
