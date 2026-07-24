"""Clause-anchored regulation search (Track C, T3.3 Part 1).

:class:`RegulationSearch` is the thin service that both the contract's
``search_regulations`` tool (``tools.py``) and the T3.5 agent call. It sits on
top of the T3.2 :class:`~cobol_archaeologist.rag.index.RegulationIndex` and does
the one piece of real work the tool contract requires: mapping each retrieved
**chunk** back to the **clause record** it came from, because ``RegulationIndex``
ranks ``RegulationChunk``s while ``RegSearchHit`` wraps a ``RegulationClause``
(the record carries ``current_value``, which chunks lack and the agent needs).

The mapping (see :func:`map_hits_to_clause_hits`) is not a pass-through:

- **Join** each chunk's ``(doc, clause_id)`` to the ``clause`` sub-object of the
  matching record in ``data/regulations/clauses.jsonl``.
- **Drop** chunks whose ``clause_id`` is ``None`` (front matter, annexes,
  un-numbered definitions) — the tool contractually returns clause-anchored
  hits, so an un-numbered chunk has no clause to return. Also drop chunks whose
  ``(doc, clause_id)`` is not an anchored record; a returned hit is always a
  real ``clauses.jsonl`` clause.
- **Deduplicate** to one hit per clause: a multi-chunk clause is collapsed,
  keeping the best (max) score, at the rank of its first (best) appearance.

HyDE query transformation (``use_hyde``) is accepted here for forward
compatibility but is a no-op in this build — it lands in T3.3b (Part 2).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cobol_archaeologist.rag.index import (
    CLAUSES,
    CORPUS_FIXTURE,
    Hit,
    RegulationIndex,
    load_corpus,
    load_jsonl,
)
from cobol_archaeologist.schemas import RegulationClause
from cobol_archaeologist.tool_types import RegSearchHit

# hybrid_rerank returns at most rerank_depth (20) chunks; a floor at that depth
# lets dedup + None-dropping still fill k clauses from the retrieved pool.
_POOL_FLOOR = 20


def load_clause_lookup(
    clauses_path: Path = CLAUSES,
) -> dict[tuple[str, str], RegulationClause]:
    """``(doc, clause_id) -> RegulationClause`` over every record in
    ``clauses.jsonl``. The value is the record's ``clause`` sub-object (the
    frozen :class:`RegulationClause`, carrying ``current_value``)."""
    lookup: dict[tuple[str, str], RegulationClause] = {}
    for record in load_jsonl(Path(clauses_path)):
        clause = RegulationClause.model_validate(record["clause"])
        lookup[(clause.doc, clause.clause_id)] = clause
    return lookup


def map_hits_to_clause_hits(
    hits: Sequence[Hit],
    clause_lookup: dict[tuple[str, str], RegulationClause],
    k: int,
) -> list[RegSearchHit]:
    """Chunk hits -> clause-anchored hits: drop un-anchored chunks, dedup to one
    hit per clause (best score, first-appearance rank), truncate to ``k``.

    ``hits`` is assumed ranked best-first (as ``RegulationIndex.search`` returns
    it), so a clause's first appearance is its best rank and, for score-ordered
    modes, already its best score; the max-score guard keeps that invariant even
    if a later chunk of the same clause scores higher.
    """
    best: dict[tuple[str, str], RegSearchHit] = {}
    order: list[tuple[str, str]] = []
    for hit in hits:
        chunk = hit.chunk
        if chunk.clause_id is None:
            continue  # un-numbered chunk: no clause record to anchor to
        key = (chunk.doc, chunk.clause_id)
        clause = clause_lookup.get(key)
        if clause is None:
            continue  # chunk's clause is not an anchored clauses.jsonl record
        current = best.get(key)
        if current is None:
            best[key] = RegSearchHit(clause=clause, score=hit.score)
            order.append(key)
        elif hit.score > current.score:
            best[key] = RegSearchHit(clause=clause, score=hit.score)
    return [best[key] for key in order][:k]


class RegulationSearch:
    """Clause-anchored search over the regulation corpus.

    ``mode`` is any :class:`RegulationIndex` mode; the pinned default
    ``hybrid_rerank`` needs the T3.2 models, so when it (or another dense mode)
    is requested and no ``embedder``/``reranker`` is injected, the pinned models
    are built lazily. Tests drive the offline mapping gates with ``mode="bm25"``,
    which needs no model. ``use_hyde`` is accepted but ignored in this build
    (HyDE is T3.3b).
    """

    def __init__(
        self,
        chunks_path: Path = CORPUS_FIXTURE,
        clauses_path: Path = CLAUSES,
        mode: str = "hybrid_rerank",
        use_hyde: bool = False,
        embedder=None,
        reranker=None,
    ) -> None:
        self.mode = mode
        self.use_hyde = use_hyde  # accepted for T3.3b; a no-op here
        if mode != "bm25" and embedder is None and reranker is None:
            from cobol_archaeologist.rag.embed import DenseEmbedder, Reranker

            embedder, reranker = DenseEmbedder(), Reranker()
        self._index = RegulationIndex.build(
            load_corpus(Path(chunks_path)), embedder=embedder, reranker=reranker
        )
        self._clauses = load_clause_lookup(Path(clauses_path))

    def search(self, query: str, k: int = 5) -> list[RegSearchHit]:
        # Over-fetch: None-dropping and dedup shrink the pool, so retrieve enough
        # chunks to still return up to k distinct anchored clauses.
        pool = self._index.search(query, k=max(k * 4, _POOL_FLOOR), mode=self.mode)
        return map_hits_to_clause_hits(pool, self._clauses, k)
