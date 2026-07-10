"""RAG chunk schemas for regulation retrieval units (Track C, T3.1)."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class RegulationChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc: str
    heading_path: list[str]
    clause_id: str | None
    version: str
    effective_date: datetime.date
    text: str
    page_start: int
    page_end: int
    char_span: tuple[int, int]
