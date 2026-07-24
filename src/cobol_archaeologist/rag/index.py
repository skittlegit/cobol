"""Regulation retrieval index (Track C, T3.2).

``RegulationIndex.build(chunks)`` builds an Okapi-BM25 lexical index (always,
offline) and — when a dense embedder is supplied — dense passage vectors.
``search(query, k=5, doc=None, mode=...)`` serves four modes:

    "bm25"          lexical only (offline)
    "dense"         bi-encoder cosine
    "hybrid"        BM25 + dense fused by reciprocal-rank fusion
    "hybrid_rerank" hybrid top-N reranked by the cross-encoder (top-20 -> top-k)

``doc`` optionally restricts the candidate set to one document (T6 needs
old-side-only search). This module lands the retrieval engine; wiring it into
``ToolLayer.search_regulations`` is the T3.5 seam.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cobol_archaeologist.rag.schemas import RegulationChunk

ROOT = Path(__file__).resolve().parents[3]
CLAUSES = ROOT / "data" / "regulations" / "clauses.jsonl"
QUERIES = ROOT / "tests" / "fixtures" / "retrieval" / "queries.jsonl"
CORPUS_FIXTURE = ROOT / "tests" / "fixtures" / "retrieval" / "chunks.jsonl"
REPORT_MD = ROOT / "docs" / "tasks" / "T3.2-work-order.md"
REPORT_BEGIN = "<!-- BEGIN GENERATED RELEVANCE REPORT -->"
REPORT_END = "<!-- END GENERATED RELEVANCE REPORT -->"

MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    ["a", "an", "and", "any", "are", "as", "at", "be", "been", "by", "for", "from", "has", "have", "if", "in", "into", "is", "it", "its", "may", "must", "no", "not", "of", "on", "or", "shall", "so", "than", "that", "the", "their", "them", "then", "there", "these", "this", "to", "was", "were", "which", "who", "will", "with", "within", "without"]
)


# --- tokenisation --------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords, light-stem.

    COBOL identifiers (``WS-DAYS-SINCE-ISSUE``) split on the hyphen so they match
    natural-language clause text; numeric literals ("30", "500") survive.
    """
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in _STOPWORDS or len(raw) < 2:
            continue
        out.append(_stem(raw))
    return out


def _stem(word: str) -> str:
    if word.isdigit():
        return word
    for suffix, keep in (
        ("ations", "ate"),
        ("ation", "ate"),
        ("ements", "e"),
        ("ement", "e"),
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + keep
    for suffix in ("ings", "ing", "edly", "ed", "ies", "ied", "es", "s", "ly", "al"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            if suffix in ("ies", "ied"):
                return base + "y"
            return base
    return word


# --- fusion primitives ---------------------------------------------------------


def _rank_order(scores: Sequence[float], ids: Sequence[str]) -> list[int]:
    """Indices sorted by score desc; ties broken by chunk_id for determinism."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], ids[i]))


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]], ids: Sequence[str], k: int = 60
) -> list[tuple[int, float]]:
    """Fuse ranked index lists by RRF: score(d) = sum 1/(k + rank_r(d)).

    Returns ``(candidate index, RRF score)`` pairs, ranked desc (ties broken by
    chunk_id). Callers that only want the ranking take the first element; the
    ``hybrid`` mode carries the score through into ``Hit`` (F8 fix — hybrid hits
    previously all reported score 0.0).
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
    order = sorted(fused, key=lambda i: (-fused[i], ids[i]))
    return [(i, fused[i]) for i in order]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# --- BM25 ----------------------------------------------------------------------


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[Counter[str]] = []
        self._len: list[int] = []
        self._avg: float = 0.0
        self._idf: dict[str, float] = {}

    def fit(self, corpus: Sequence[str]) -> BM25:
        self._docs = [Counter(tokenize(t)) for t in corpus]
        self._len = [sum(d.values()) for d in self._docs]
        n = len(self._docs)
        self._avg = (sum(self._len) / n) if n else 0.0
        df: Counter[str] = Counter()
        for d in self._docs:
            for term in d:
                df[term] += 1
        self._idf = {
            t: math.log((n - f + 0.5) / (f + 0.5) + 1.0) for t, f in df.items()
        }
        return self

    def scores(self, query: str, candidates: Sequence[int]) -> list[float]:
        q = tokenize(query)
        out = []
        for i in candidates:
            if self._avg == 0.0:
                out.append(0.0)
                continue
            doc = self._docs[i]
            norm = self.k1 * (1.0 - self.b + self.b * self._len[i] / self._avg)
            s = 0.0
            for term in q:
                tf = doc.get(term, 0)
                if tf:
                    s += self._idf.get(term, 0.0) * (tf * (self.k1 + 1.0)) / (tf + norm)
            out.append(s)
        return out


# --- index ---------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    chunk: RegulationChunk
    score: float


class RegulationIndex:
    def __init__(
        self,
        chunks: Sequence[RegulationChunk],
        bm25: BM25,
        embedder=None,
        reranker=None,
        passage_vectors: list[list[float]] | None = None,
        rrf_k: int = 60,
        rerank_depth: int = 20,
    ) -> None:
        self.chunks = list(chunks)
        self.ids = [c.chunk_id for c in self.chunks]
        self.bm25 = bm25
        self.embedder = embedder
        self.reranker = reranker
        self._vectors = passage_vectors
        self.rrf_k = rrf_k
        self.rerank_depth = rerank_depth

    @classmethod
    def build(
        cls,
        chunks: Sequence[RegulationChunk],
        embedder=None,
        reranker=None,
        **kwargs,
    ) -> RegulationIndex:
        chunks = list(chunks)
        bm25 = BM25().fit([c.text for c in chunks])
        vectors = None
        if embedder is not None:
            vectors = embedder.encode_passages([c.text for c in chunks])
        return cls(chunks, bm25, embedder, reranker, vectors, **kwargs)

    def _candidates(self, doc: str | None) -> list[int]:
        if doc is None:
            return list(range(len(self.chunks)))
        return [i for i, c in enumerate(self.chunks) if c.doc == doc]

    def _dense_scores(self, query: str, candidates: Sequence[int]) -> list[float]:
        if self.embedder is None or self._vectors is None:
            raise RuntimeError("dense retrieval requires an embedder; build with one")
        qv = self.embedder.encode_query(query)
        return [cosine(qv, self._vectors[i]) for i in candidates]

    def search(
        self,
        query: str,
        k: int = 5,
        doc: str | None = None,
        mode: str = "hybrid_rerank",
    ) -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
        cand = self._candidates(doc)
        if not cand:
            return []
        cand_ids = [self.ids[i] for i in cand]

        if mode == "bm25":
            scores = self.bm25.scores(query, cand)
            order = _rank_order(scores, cand_ids)
            return [Hit(self.chunks[cand[j]], scores[j]) for j in order[:k]]

        if mode == "dense":
            scores = self._dense_scores(query, cand)
            order = _rank_order(scores, cand_ids)
            return [Hit(self.chunks[cand[j]], scores[j]) for j in order[:k]]

        # hybrid / hybrid_rerank: fuse BM25 + dense over the candidate set.
        bm25_scores = self.bm25.scores(query, cand)
        dense_scores = self._dense_scores(query, cand)
        fused = reciprocal_rank_fusion(
            [_rank_order(bm25_scores, cand_ids), _rank_order(dense_scores, cand_ids)],
            cand_ids,
            k=self.rrf_k,
        )
        if mode == "hybrid":
            return [Hit(self.chunks[cand[j]], rrf) for j, rrf in fused[:k]]

        # hybrid_rerank: rerank the fused head with the cross-encoder.
        if self.reranker is None:
            raise RuntimeError("hybrid_rerank requires a reranker; build with one")
        head = [j for j, _ in fused[: self.rerank_depth]]
        rr = self.reranker.score(query, [self.chunks[cand[j]].text for j in head])
        ranked = sorted(range(len(head)), key=lambda p: (-rr[p], cand_ids[head[p]]))
        return [Hit(self.chunks[cand[head[p]]], rr[p]) for p in ranked[:k]]


# --- gold resolution + metrics -------------------------------------------------


def load_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_corpus(path: Path = CORPUS_FIXTURE) -> list[RegulationChunk]:
    return [RegulationChunk.model_validate(r) for r in load_jsonl(path)]


@dataclass(frozen=True)
class GoldQuery:
    query_id: str
    record_id: str
    query: str
    note: str
    gold_doc: str
    gold_clause_id: str | None


def resolve_gold_queries(
    queries_path: Path = QUERIES, clauses_path: Path = CLAUSES
) -> list[GoldQuery]:
    """Resolve each query's gold live: record_id -> (clause.doc, clause.clause_id)."""
    clause_by_record = {r["record_id"]: r["clause"] for r in load_jsonl(clauses_path)}
    out: list[GoldQuery] = []
    for q in load_jsonl(queries_path):
        clause = clause_by_record[q["record_id"]]
        out.append(
            GoldQuery(
                q["query_id"],
                q["record_id"],
                q["query"],
                q.get("note", ""),
                clause["doc"],
                clause["clause_id"],
            )
        )
    return out


def _is_gold(hit: Hit, gq: GoldQuery) -> bool:
    return hit.chunk.doc == gq.gold_doc and hit.chunk.clause_id == gq.gold_clause_id


def rank_of_gold(hits: Sequence[Hit], gq: GoldQuery) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if _is_gold(hit, gq):
            return rank
    return None


def mode_metrics(ranks: Sequence[int | None]) -> dict[str, float]:
    n = len(ranks)

    def hit_at(k: int) -> float:
        return sum(1 for r in ranks if r is not None and r <= k) / n

    mrr5 = sum((1.0 / r) for r in ranks if r is not None and r <= 5) / n
    return {"hit@1": hit_at(1), "hit@3": hit_at(3), "mrr@5": mrr5}


def evaluate_modes(
    index: RegulationIndex, queries: Sequence[GoldQuery], k: int = 5
) -> dict:
    per_mode_ranks: dict[str, list[int | None]] = {m: [] for m in MODES}
    per_query: list[dict] = []
    for gq in queries:
        row = {"query_id": gq.query_id, "record_id": gq.record_id, "note": gq.note}
        for m in MODES:
            r = rank_of_gold(index.search(gq.query, k=k, mode=m), gq)
            per_mode_ranks[m].append(r)
            row[m] = r
        per_query.append(row)
    return {
        "metrics": {m: mode_metrics(per_mode_ranks[m]) for m in MODES},
        "per_query": per_query,
    }


# --- relevance report (Gate B, network) ----------------------------------------

_PROBE_IDS = {"q20", "q21", "q22", "q23", "q24"}


def _fmt(r: int | None) -> str:
    return "–" if r is None else str(r)


def _mode_table(metrics: dict) -> list[str]:
    rows = ["| mode | hit@1 | hit@3 | mrr@5 |", "|---|---|---|---|"]
    for m in MODES:
        d = metrics[m]
        rows.append(f"| {m} | {d['hit@1']:.3f} | {d['hit@3']:.3f} | {d['mrr@5']:.3f} |")
    return rows


def _perquery_table(per_query: list[dict], only: set[str] | None = None) -> list[str]:
    rows = ["| query | " + " | ".join(MODES) + " |", "|---|" + "---|" * len(MODES)]
    for row in per_query:
        if only is not None and row["query_id"] not in only:
            continue
        cells = " | ".join(_fmt(row[m]) for m in MODES)
        rows.append(f"| {row['query_id']} ({row['record_id']}) | {cells} |")
    return rows


def _write_relevance_report(report_path: Path, lines: Sequence[str]) -> None:
    """Write a standalone report or replace the canonical work-order block."""
    rendered = "\n".join(lines).rstrip() + "\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if REPORT_BEGIN in existing and REPORT_END in existing:
        prefix, remainder = existing.split(REPORT_BEGIN, 1)
        _, suffix = remainder.split(REPORT_END, 1)
        output = f"{prefix}{REPORT_BEGIN}\n{rendered}{REPORT_END}{suffix}"
    else:
        output = f"# T3.2 — Retrieval relevance report\n\n{rendered}"
    report_path.write_text(output, encoding="utf-8")


def build_relevance_report(
    report_path: Path = REPORT_MD, k: int = 5, corpus_path: Path = CORPUS_FIXTURE
) -> dict:
    """Run all four modes over the fixed query set and emit the markdown report.

    Network: loads the pinned models. Determines pass/fail on the done-when bar.
    """
    from cobol_archaeologist.rag.embed import (
        EMBEDDER_MODEL,
        EMBEDDER_REVISION,
        RERANKER_MODEL,
        RERANKER_REVISION,
        DenseEmbedder,
        Reranker,
    )

    chunks = load_corpus(corpus_path)
    queries = resolve_gold_queries()
    index = RegulationIndex.build(chunks, embedder=DenseEmbedder(), reranker=Reranker())
    result = evaluate_modes(index, queries, k=k)
    metrics = result["metrics"]

    hybrid_rr = metrics["hybrid_rerank"]
    dense = metrics["dense"]
    bar_met = (
        hybrid_rr["mrr@5"] > dense["mrr@5"]
        and hybrid_rr["hit@1"] >= dense["hit@1"]
        and hybrid_rr["hit@3"] >= dense["hit@3"]
    )

    lines = [
        "## Relevance evidence",
        "",
        (
            f"- Corpus: {len(chunks)} chunks over "
            f"{len({c.doc for c in chunks})} documents "
            f"(`{corpus_path.relative_to(ROOT).as_posix()}`)."
        ),
        f"- Queries: {len(queries)} (fixed set; {len(_PROBE_IDS)} confusion probes).",
        f"- Embedder: `{EMBEDDER_MODEL}` @ `{EMBEDDER_REVISION}`.",
        f"- Reranker: `{RERANKER_MODEL}` @ `{RERANKER_REVISION}`.",
        f"- Metric: gold = returned chunk with matching (doc, clause_id); k={k}.",
        "",
        (
            "**Done-when bar:** `hybrid_rerank` beats `dense` on mrr@5, "
            f"≥ on hit@1/hit@3 — **{'MET' if bar_met else 'NOT MET'}**."
        ),
        "",
        "## Mode comparison",
        "",
        *_mode_table(metrics),
        "",
        "## Confusion probes (q20–q24)",
        "",
        *_perquery_table(result["per_query"], only=_PROBE_IDS),
        "",
        "## Per-query rank of gold (all modes)",
        "",
        *_perquery_table(result["per_query"]),
        "",
    ]
    _write_relevance_report(report_path, lines)
    result["bar_met"] = bar_met
    return result


if __name__ == "__main__":
    r = build_relevance_report()
    for m in MODES:
        print(m, {k: round(v, 3) for k, v in r["metrics"][m].items()})
    print("bar_met:", r["bar_met"])
