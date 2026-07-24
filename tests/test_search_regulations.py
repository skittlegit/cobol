"""T3.3 Part 1 gates — `search_regulations` wiring (chunk -> clause mapping).

The real work of Part 1 is mapping retrieved ``RegulationChunk``s back to the
``RegulationClause`` records the tool contract returns. These gates pin that
mapping so a later change cannot silently regress it:

- clause-anchored: every hit is a real ``clauses.jsonl`` clause;
- no ``clause_id=None`` chunk leaks through (expected drop, asserted so it is
  not "fixed" later);
- dedup: one hit per clause, keeping the best score;
- contract shape: ``list[RegSearchHit]``, ``len <= k``;
- isinstance parity: ``RealToolLayer`` still satisfies ``ToolLayer`` and
  ``search_regulations`` no longer raises.

All offline: the mapping gates drive ``RegulationSearch`` in ``mode="bm25"`` (no
model weights), and the mapper is unit-tested with synthetic chunks. Dense/HyDE
behaviour is out of scope here (HyDE is T3.3b).
"""

import datetime
from pathlib import Path

import pytest

from cobol_archaeologist import tool_types
from cobol_archaeologist.rag.index import Hit
from cobol_archaeologist.rag.schemas import RegulationChunk
from cobol_archaeologist.rag.search import (
    RegulationSearch,
    load_clause_lookup,
    map_hits_to_clause_hits,
)
from cobol_archaeologist.schemas import RegulationClause
from cobol_archaeologist.tool_types import RegSearchHit

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"
CBL_DIR = CARDDEMO / "app" / "cbl"
CPY_DIRS = [CARDDEMO / "app" / "cpy", CARDDEMO / "app" / "cpy-bms"]

# A query whose bm25 head contains anchored clauses — the integration path.
ANCHORED_QUERY = "periodic updation of KYC records risk category high medium low"


@pytest.fixture(scope="module")
def anchored_keys() -> set[tuple[str, str]]:
    return set(load_clause_lookup())


@pytest.fixture(scope="module")
def search() -> RegulationSearch:
    # bm25: offline, no model weights — exercises the real mapping path.
    return RegulationSearch(mode="bm25")


# --- synthetic-chunk helpers for the mapper unit gates -------------------------


def _chunk(chunk_id: str, doc: str, clause_id: str | None) -> RegulationChunk:
    return RegulationChunk(
        chunk_id=chunk_id,
        doc=doc,
        heading_path=[],
        clause_id=clause_id,
        version="2025-11-28",
        effective_date=datetime.date(2025, 11, 28),
        text=f"text of {chunk_id}",
        page_start=1,
        page_end=1,
        char_span=(0, 10),
    )


def _clause(doc: str, clause_id: str) -> RegulationClause:
    return RegulationClause(
        doc=doc,
        clause_id=clause_id,
        version="2025-11-28",
        effective_date=datetime.date(2025, 11, 28),
        text=f"clause {clause_id}",
    )


# --- mapper unit gates (fully synthetic, deterministic) ------------------------


def test_mapper_drops_none_clause_id_chunks():
    doc = "D"
    lookup = {(doc, "1"): _clause(doc, "1")}
    hits = [
        Hit(_chunk("c-none", doc, None), 9.0),   # un-numbered: must be dropped
        Hit(_chunk("c-1", doc, "1"), 5.0),
    ]
    out = map_hits_to_clause_hits(hits, lookup, k=5)
    assert [h.clause.clause_id for h in out] == ["1"]
    assert all(h.clause.clause_id is not None for h in out)


def test_mapper_drops_chunks_with_no_anchored_clause():
    doc = "D"
    lookup = {(doc, "1"): _clause(doc, "1")}
    hits = [
        Hit(_chunk("c-x", doc, "999"), 9.0),  # not an anchored record: dropped
        Hit(_chunk("c-1", doc, "1"), 5.0),
    ]
    out = map_hits_to_clause_hits(hits, lookup, k=5)
    assert [(h.clause.doc, h.clause.clause_id) for h in out] == [(doc, "1")]


def test_mapper_dedups_to_one_hit_per_clause_keeping_max_score():
    doc = "D"
    lookup = {(doc, "1"): _clause(doc, "1")}
    hits = [
        Hit(_chunk("c-1a", doc, "1"), 5.0),
        Hit(_chunk("c-1b", doc, "1"), 8.0),  # same clause, higher score
        Hit(_chunk("c-1c", doc, "1"), 3.0),
    ]
    out = map_hits_to_clause_hits(hits, lookup, k=5)
    assert len(out) == 1
    assert out[0].score == 8.0  # best score wins


def test_mapper_truncates_to_k():
    doc = "D"
    lookup = {(doc, str(i)): _clause(doc, str(i)) for i in range(5)}
    hits = [Hit(_chunk(f"c{i}", doc, str(i)), float(5 - i)) for i in range(5)]
    out = map_hits_to_clause_hits(hits, lookup, k=2)
    assert len(out) == 2
    # first-appearance (best-rank) order preserved
    assert [h.clause.clause_id for h in out] == ["0", "1"]


# --- integration gates over the real corpus (offline bm25) ---------------------


def test_results_are_clause_anchored(search, anchored_keys):
    hits = search.search(ANCHORED_QUERY, k=5)
    assert hits, "query should surface at least one anchored clause"
    for h in hits:
        assert isinstance(h.clause, RegulationClause)
        assert (h.clause.doc, h.clause.clause_id) in anchored_keys


def test_no_clause_id_none_leaks(search):
    hits = search.search(ANCHORED_QUERY, k=5)
    assert all(h.clause.clause_id is not None for h in hits)


def test_dedup_no_clause_appears_twice(search):
    hits = search.search(ANCHORED_QUERY, k=5)
    keys = [(h.clause.doc, h.clause.clause_id) for h in hits]
    assert len(keys) == len(set(keys))


def test_returns_regsearchhit_list_len_le_k(search):
    k = 3
    hits = search.search(ANCHORED_QUERY, k=k)
    assert isinstance(hits, list)
    assert all(isinstance(h, RegSearchHit) for h in hits)
    assert len(hits) <= k


def test_use_hyde_is_accepted_but_inert(anchored_keys):
    # Part 1 accepts use_hyde without changing results (HyDE lands in T3.3b).
    base = RegulationSearch(mode="bm25", use_hyde=False)
    hyde = RegulationSearch(mode="bm25", use_hyde=True)
    a = [(h.clause.doc, h.clause.clause_id) for h in base.search(ANCHORED_QUERY, k=5)]
    b = [(h.clause.doc, h.clause.clause_id) for h in hyde.search(ANCHORED_QUERY, k=5)]
    assert a == b


# --- isinstance parity + delegation (corpora-backed) ---------------------------


def test_realtoollayer_is_still_a_toollayer_class():
    # Protocol conformance is structural; search_regulations no longer raising
    # does not change the class's membership, but pin it so a signature edit that
    # would break the seam is caught here too.
    from cobol_archaeologist.tools import RealToolLayer

    assert issubclass(RealToolLayer, tool_types.ToolLayer)


@pytest.mark.skipif(
    not CARDDEMO.is_dir(), reason="corpora not fetched (run scripts/fetch_corpora.sh)"
)
def test_search_regulations_delegates_and_no_longer_raises(search):
    from cobol_archaeologist.tools import RealToolLayer

    layer = RealToolLayer(corpus_root=CBL_DIR, copybook_paths=CPY_DIRS)
    assert isinstance(layer, tool_types.ToolLayer)
    # Inject the offline (bm25) service so the delegation path runs without model
    # weights; proves the method is wired and NotImplementedError is gone.
    layer._reg_search = search
    hits = layer.search_regulations(ANCHORED_QUERY)
    assert isinstance(hits, list)
    assert all(isinstance(h, RegSearchHit) for h in hits)
    assert len(hits) <= 5
