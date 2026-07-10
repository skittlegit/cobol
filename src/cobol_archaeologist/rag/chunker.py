"""Structure-aware regulation chunker (Track C, T3.1)."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

from cobol_archaeologist.rag.pdf_loader import LoadedPdf, load_pdf
from cobol_archaeologist.rag.schemas import RegulationChunk

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "data" / "regulations" / "sources"
MANIFEST = SOURCES / "MANIFEST.json"
CLAUSES = ROOT / "data" / "regulations" / "clauses.jsonl"
OUTPUT_DIR = ROOT / "data" / "regulations" / "chunks"
BOUNDARY_REPORT = ROOT / "tests" / "fixtures" / "chunks" / "anchor-boundary-report.json"
ANCHOR_FILE = "cc-dc-directions-2025.pdf"

TOP_CLAUSE_RE = re.compile(r"^(\d+)\.\s+(.*)")
SUBCLAUSE_RE = re.compile(r"^\(([A-Za-z]+|[ivxlcdmIVXLCDM]+|\d+)\)\s+(.*)")
CHAPTER_RE = re.compile(r"^(Chapter\s+[IVXLC]+)\s+[\u2013-]\s+(.+)$", re.I)
LETTER_HEADING_RE = re.compile(r"^([A-Z])\.\s+(.+)$")
TOC_DOT_RE = re.compile(r"\.{4,}\s*\d+\s*$")
WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ManifestEntry:
    file: str
    doc: str
    version: str
    effective_date: dt.date
    status: str


@dataclass(frozen=True)
class TextLine:
    text: str
    start: int
    end: int
    page: int


@dataclass(frozen=True)
class Segment:
    kind: str
    title: str
    clause_id: str | None
    path: list[str]
    start: int
    end: int
    page_start: int
    page_end: int


def main() -> None:
    chunks = build_all_chunks()
    write_chunks(chunks)
    write_anchor_boundary_report(chunks)


def build_all_chunks() -> list[RegulationChunk]:
    clause_records = load_clause_records()
    chunks: list[RegulationChunk] = []
    for entry in load_manifest_entries():
        if entry.status != "pinned":
            continue
        loaded = load_pdf(SOURCES / entry.file)
        doc_chunks = chunk_loaded_pdf(loaded, entry)
        doc_chunks = reconcile_clause_vocabulary(doc_chunks, clause_records)
        chunks.extend(doc_chunks)
    return sorted(chunks, key=lambda c: (c.doc, c.page_start, c.char_span, c.chunk_id))


def write_chunks(chunks: list[RegulationChunk], output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    by_doc: dict[str, list[RegulationChunk]] = {}
    for chunk in chunks:
        by_doc.setdefault(chunk.doc, []).append(chunk)
    for doc, doc_chunks in by_doc.items():
        path = output_dir / f"{slugify(doc)}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for chunk in doc_chunks:
                fh.write(chunk.model_dump_json() + "\n")


def write_anchor_boundary_report(
    chunks: list[RegulationChunk], report_path: Path = BOUNDARY_REPORT
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    anchor = [
        {
            "clause_id": chunk.clause_id,
            "heading_path": chunk.heading_path,
            "page_start": chunk.page_start,
            "first_60": _snippet(chunk.text[:60]),
            "last_60": _snippet(chunk.text[-60:]),
        }
        for chunk in chunks
        if chunk.doc == "RBI-Commercial-Banks-CC-DC-Directions-2025"
    ]
    report_path.write_text(
        json.dumps(anchor, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_manifest_entries(path: Path = MANIFEST) -> list[ManifestEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for raw in data["entries"]:
        if raw.get("status") != "pinned":
            continue
        missing = [key for key in ("doc", "version", "effective_date") if key not in raw]
        if missing:
            raise ValueError(f"{raw.get('file')}: missing T3.1 manifest fields {missing}")
        entries.append(
            ManifestEntry(
                file=raw["file"],
                doc=raw["doc"],
                version=raw["version"],
                effective_date=dt.date.fromisoformat(raw["effective_date"]),
                status=raw["status"],
            )
        )
    return entries


def load_clause_records(path: Path = CLAUSES) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def chunk_loaded_pdf(loaded: LoadedPdf, entry: ManifestEntry) -> list[RegulationChunk]:
    lines = list(_iter_lines(loaded))
    segments = _segments(lines, len(loaded.text))
    chunks = []
    counters: dict[str, int] = {}
    for segment in segments:
        text = loaded.text[segment.start : segment.end].strip()
        if not text:
            continue
        if segment.clause_id is None:
            counters["front"] = counters.get("front", 0) + 1
            local_id = f"front-{counters['front']}"
        else:
            local_id = segment.clause_id
        chunks.append(
            RegulationChunk(
                chunk_id=f"{slugify(entry.file.removesuffix('.pdf'))}::{local_id}",
                doc=entry.doc,
                heading_path=segment.path,
                clause_id=segment.clause_id,
                version=entry.version,
                effective_date=entry.effective_date,
                text=text,
                page_start=segment.page_start,
                page_end=segment.page_end,
                char_span=(segment.start, segment.end),
            )
        )
    return chunks


def reconcile_clause_vocabulary(
    chunks: list[RegulationChunk], clause_records: list[dict]
) -> list[RegulationChunk]:
    out = list(chunks)
    by_key = {(chunk.doc, chunk.clause_id): chunk for chunk in out if chunk.clause_id}
    for record in clause_records:
        clause = record["clause"]
        key = (clause["doc"], clause["clause_id"])
        if key in by_key:
            continue
        if clause["doc"] not in {chunk.doc for chunk in out}:
            continue
        match = _best_subset_match(out, clause)
        if match is None:
            continue
        out.remove(match)
        out.append(
            match.model_copy(
                update={
                    "chunk_id": f"{match.chunk_id.rsplit('::', 1)[0]}::{clause['clause_id']}",
                    "clause_id": clause["clause_id"],
                    "heading_path": [*match.heading_path, clause["clause_id"]],
                }
            )
        )
    return sorted(out, key=lambda c: (c.doc, c.page_start, c.char_span, c.chunk_id))


def _best_subset_match(chunks: list[RegulationChunk], clause: dict) -> RegulationChunk | None:
    candidates = [chunk for chunk in chunks if chunk.doc == clause["doc"]]
    scored = [
        (_content_overlap(clause["text"], chunk.text), len(chunk.text), chunk)
        for chunk in candidates
    ]
    scored.sort(key=lambda item: (-item[0], item[1], item[2].char_span))
    threshold = 0.68 if str(clause["clause_id"]).startswith("PROVISIONAL:") else 0.8
    if scored and scored[0][0] >= threshold:
        return scored[0][2]
    return None


def _segments(lines: list[TextLine], doc_end: int) -> list[Segment]:
    starts: list[tuple[int, TextLine, str, str | None, list[str]]] = []
    chapter: str | None = None
    section: str | None = None
    current_top: str | None = None
    current_top_title: str | None = None

    for line in lines:
        if _is_toc_line(line.text):
            continue
        chapter_match = CHAPTER_RE.match(line.text)
        if chapter_match:
            chapter = f"{chapter_match.group(1)} \u2013 {chapter_match.group(2).strip()}"
            section = None
            starts.append((line.start, line, "front", None, [chapter]))
            continue
        letter_match = LETTER_HEADING_RE.match(line.text)
        if letter_match and current_top is not None:
            section = f"{letter_match.group(1)}. {letter_match.group(2).strip()}"
            starts.append((line.start, line, "front", None, _path(chapter, section)))
            continue
        top_match = TOP_CLAUSE_RE.match(line.text)
        if top_match:
            current_top = normalize_clause_id(top_match.group(1))
            current_top_title = _title(top_match.group(2))
            starts.append(
                (
                    line.start,
                    line,
                    "clause",
                    current_top,
                    _path(chapter, section, f"{current_top}. {current_top_title}"),
                )
            )
            continue
        sub_match = SUBCLAUSE_RE.match(line.text)
        if sub_match and current_top is not None:
            if sub_match.group(2).lower().startswith("of "):
                continue
            sub_id = normalize_clause_id(f"{current_top}({sub_match.group(1)})")
            starts.append(
                (
                    line.start,
                    line,
                    "clause",
                    sub_id,
                    _path(
                        chapter,
                        section,
                        f"{current_top}. {current_top_title or ''}".strip(),
                        f"({normalize_part(sub_match.group(1))})",
                    ),
                )
            )

    if not starts and lines:
        starts.append((lines[0].start, lines[0], "front", None, ["Document"]))
    elif starts and lines and starts[0][0] > lines[0].start:
        starts.insert(0, (lines[0].start, lines[0], "front", None, ["Front matter"]))

    segments: list[Segment] = []
    for i, (start, line, kind, clause_id, path) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else doc_end
        if end <= start:
            continue
        segments.append(
            Segment(
                kind=kind,
                title=path[-1] if path else "",
                clause_id=clause_id,
                path=path,
                start=start,
                end=end,
                page_start=line.page,
                page_end=_page_for_offset(lines, end),
            )
        )
    return segments


def _iter_lines(loaded: LoadedPdf) -> list[TextLine]:
    lines: list[TextLine] = []
    for page in loaded.pages:
        offset = page.char_start
        for raw in page.text.splitlines(keepends=True):
            text = raw.strip()
            start = offset + len(raw) - len(raw.lstrip())
            end = offset + len(raw.rstrip("\r\n"))
            offset += len(raw)
            if text:
                lines.append(TextLine(text=text, start=start, end=end, page=page.page_number))
    return lines


def _page_for_offset(lines: list[TextLine], offset: int) -> int:
    page = lines[0].page if lines else 1
    for line in lines:
        if line.start >= offset:
            break
        page = line.page
    return page


def normalize_clause_id(raw: str) -> str:
    raw = re.sub(r"\s+", "", raw)
    return re.sub(r"\(([^)]+)\)", lambda m: f"({normalize_part(m.group(1))})", raw)


def normalize_part(raw: str) -> str:
    return raw.strip().lower()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "document"


def _path(*parts: str | None) -> list[str]:
    return [part for part in parts if part]


def _title(text: str) -> str:
    title = text.strip()
    title = TOC_DOT_RE.sub("", title).strip()
    return title.rstrip(":") or "Clause"


def _is_toc_line(text: str) -> bool:
    return bool(TOC_DOT_RE.search(text))


def _snippet(text: str) -> str:
    return " ".join(text.split())


def _content_words(text: str) -> set[str]:
    stop = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "or",
        "shall",
        "the",
        "to",
        "with",
        "must",
        "may",
        "can",
        "should",
        "maximum",
        "minimum",
        "amendment",
        "lowered",
        "regulated",
        "registry",
        "rbi",
        "they",
        "have",
        "without",
        "within",
        "receiving",
        "carried",
    }
    words = set()
    for word in WORD_RE.findall(text.lower()):
        if len(word) > 2 and word not in stop and not re.fullmatch(r"20\d{2}", word):
            words.add(_canonical_word(word))
    return words


def _canonical_word(word: str) -> str:
    aliases = {
        "begins": "start",
        "capitalisation": "capitalize",
        "capitalise": "capitalize",
        "capitalised": "capitalize",
        "capitalized": "capitalize",
        "ckycr": "central",
        "dispatching": "send",
        "emailing": "send",
        "entities": "bank",
        "entity": "bank",
        "firms": "firm",
        "getting": "get",
        "lodging": "lodge",
        "received": "receive",
        "receives": "receive",
        "redressal": "redress",
        "satisfactory": "satisfied",
        "sending": "send",
        "sent": "send",
        "starts": "start",
        "updation": "update",
        "updated": "update",
        "updating": "update",
    }
    if word in aliases:
        return aliases[word]
    for suffix in ("ization", "isation"):
        if word.endswith(suffix) and len(word) > len(suffix) + 3:
            return word[: -len(suffix)] + "ize"
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 3:
            return word[: -len(suffix)]
    return word


def _content_overlap(needle: str, haystack: str) -> float:
    words = _content_words(needle)
    if not words:
        return 1.0
    hay = _content_words(haystack)
    return len(words & hay) / len(words)


if __name__ == "__main__":
    main()
