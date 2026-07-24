"""Offline-capable HyDE query transformation for regulation retrieval.

The fixed T3.3b evaluation queries are served from a committed cache with
generator provenance. Unseen queries use a deterministic local normalizer so
``use_hyde=True`` never introduces a cloud-only runtime dependency.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.rag.index import GoldQuery, RegulationIndex, evaluate_modes

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = ROOT / "tests" / "fixtures" / "retrieval" / "hyde_cache.json"
QUERIES = ROOT / "tests" / "fixtures" / "retrieval" / "queries.jsonl"
CACHE_SCHEMA_VERSION = 1
HYDE_PROMPT_VERSION = "t3.3b-rule-description-v1"


class HyDEProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    revision: str
    prompt_version: str
    generated_at: str
    source_queries_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class HyDERecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(pattern=r"^q\d{2}$")
    raw_query: str = Field(min_length=1)
    description: str = Field(min_length=1)


class HyDECache(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    provenance: HyDEProvenance
    records: list[HyDERecord]

    @model_validator(mode="after")
    def _unique_records(self) -> HyDECache:
        ids = [record.query_id for record in self.records]
        queries = [record.raw_query for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("HyDE cache query_id values must be unique")
        if len(queries) != len(set(queries)):
            raise ValueError("HyDE cache raw_query values must be unique")
        return self


class HyDEGenerator(Protocol):
    def describe(self, query: str) -> str: ...


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_hyde_cache(path: Path = DEFAULT_CACHE) -> HyDECache:
    cache = HyDECache.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if cache.schema_version != CACHE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported HyDE cache schema {cache.schema_version}; "
            f"expected {CACHE_SCHEMA_VERSION}"
        )
    if cache.provenance.prompt_version != HYDE_PROMPT_VERSION:
        raise ValueError("HyDE cache prompt version does not match runtime")
    if Path(path).resolve() == DEFAULT_CACHE.resolve():
        actual = _sha256(QUERIES)
        if cache.provenance.source_queries_sha256 != actual:
            raise ValueError("HyDE cache does not match the fixed query set")
    return cache


class HeuristicHyDEGenerator:
    """Deterministic local fallback for queries absent from the fixed cache."""

    _TOKEN_REPLACEMENTS = (
        (re.compile(r"\bWS-", re.IGNORECASE), ""),
        (re.compile(r"\bIF\b", re.IGNORECASE), ""),
        (re.compile(r"\bMOVE\s+['\"][^'\"]+['\"]\s+TO\b", re.IGNORECASE), ""),
        (re.compile(r"\bPERFORM\b", re.IGNORECASE), "execute"),
        (re.compile(r"\bCIC\b", re.IGNORECASE), "credit information company"),
        (re.compile(r"[-_]+"), " "),
        (re.compile(r"\s+"), " "),
    )

    def describe(self, query: str) -> str:
        normalized = query.strip()
        for pattern, replacement in self._TOKEN_REPLACEMENTS:
            normalized = pattern.sub(replacement, normalized)
        normalized = normalized.strip(" .")
        return (
            "The implemented regulatory rule requires the system to "
            f"{normalized.lower()}."
        )


class CachedHyDEGenerator:
    """Exact offline replay for the evaluation set with a local fallback."""

    # DECISION: cache the model-produced descriptions for reproducible evaluation
    # while retaining a deterministic local fallback for arbitrary runtime queries.
    # Gold record IDs and clause text are deliberately absent from both paths.
    def __init__(
        self,
        cache_path: Path = DEFAULT_CACHE,
        *,
        fallback: HyDEGenerator | None = None,
    ) -> None:
        self.cache = load_hyde_cache(cache_path)
        self._by_query = {
            record.raw_query: record.description for record in self.cache.records
        }
        self.fallback = fallback or HeuristicHyDEGenerator()

    def describe(self, query: str) -> str:
        return self._by_query.get(query, self.fallback.describe(query))


def compare_raw_and_hyde(
    index: RegulationIndex,
    queries: list[GoldQuery],
    generator: HyDEGenerator,
    *,
    k: int = 5,
) -> dict:
    """Evaluate the same fixed queries before and after HyDE transformation."""

    transformed = [
        GoldQuery(
            query_id=query.query_id,
            record_id=query.record_id,
            query=generator.describe(query.query),
            note=query.note,
            gold_doc=query.gold_doc,
            gold_clause_id=query.gold_clause_id,
        )
        for query in queries
    ]
    raw = evaluate_modes(index, queries, k=k)
    hyde = evaluate_modes(index, transformed, k=k)
    raw_by_id = {row["query_id"]: row for row in raw["per_query"]}
    hyde_by_id = {row["query_id"]: row for row in hyde["per_query"]}
    per_query = [
        {
            "query_id": query.query_id,
            "record_id": query.record_id,
            "note": query.note,
            "raw_query": query.query,
            "hyde_query": generator.describe(query.query),
            "raw": {
                mode: raw_by_id[query.query_id][mode] for mode in raw["metrics"]
            },
            "hyde": {
                mode: hyde_by_id[query.query_id][mode] for mode in hyde["metrics"]
            },
        }
        for query in queries
    ]
    return {"raw": raw, "hyde": hyde, "per_query": per_query}
