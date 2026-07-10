"""PDF text loading with page anchors for regulation chunking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class LoadedPdf:
    path: Path
    pages: list[PageText]
    text: str


def load_pdf(path: Path) -> LoadedPdf:
    """Extract text from a born-digital PDF and preserve page char offsets."""

    raw_pages = _extract_pages(path)
    cleaned_pages = _strip_page_furniture(raw_pages)
    pages: list[PageText] = []
    parts: list[str] = []
    offset = 0
    for page_number, text in enumerate(cleaned_pages, 1):
        if pages:
            parts.append("\n")
            offset += 1
        start = offset
        parts.append(text)
        offset += len(text)
        pages.append(PageText(page_number, text, start, offset))
    return LoadedPdf(path=path, pages=pages, text="".join(parts))


def _extract_pages(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [page.extract_text(x_tolerance=1, y_tolerance=3) or "" for page in pdf.pages]


def _strip_page_furniture(pages: list[str]) -> list[str]:
    line_counts: dict[str, int] = {}
    page_count = len(pages)
    for text in pages:
        seen = {_normalize_line(line) for line in text.splitlines() if line.strip()}
        for line in seen:
            line_counts[line] = line_counts.get(line, 0) + 1

    repeated = {
        line
        for line, count in line_counts.items()
        if page_count >= 3 and count >= max(3, page_count // 4)
    }
    cleaned: list[str] = []
    for text in pages:
        kept = []
        for raw in text.splitlines():
            line = raw.strip()
            norm = _normalize_line(line)
            if not line:
                continue
            if line.isdigit():
                continue
            if norm in repeated:
                continue
            kept.append(line)
        cleaned.append("\n".join(kept))
    return cleaned


def _normalize_line(line: str) -> str:
    return " ".join(line.split())
