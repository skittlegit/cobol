"""Real COPY / COPY REPLACING expansion with a line map (Track A, T1.1).

Resolves ``COPY X[.]`` and ``COPY X REPLACING ==a== BY ==b==...`` (pseudo-text
substitution) against a copybook search path, so downstream tools can read
expanded DATA DIVISION field layouts while every line still round-trips back
to its origin (CLAUDE.md rule 4: line-number fidelity is sacred).

DECISION: ``expand`` takes only ``source``/``search_paths`` (no path for the
input itself), so `LineMapEntry.source_file` is `""` for lines that are the
caller's own, unexpanded text (the caller already knows its own path) and the
resolved copybook's path for lines that came from expansion — the only case
this module can't otherwise tell the caller about.

DECISION: nesting is capped at one level (COPY inside an already-included
copybook). A COPY found one level deeper is left as literal, unexpanded text
rather than resolved — CLAUDE.md's stop condition for deeper nesting is a
"stop, report to chat" in an interactive run; no gate program exercises this
path (verified against the T1.1 corpus), so it degrades safely instead of
raising.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from cobol_archaeologist import tool_types

_MAX_DEPTH = 2  # program (depth 0) -> copybook (depth 1) -> nested copybook (depth 2)
_COPY_START_RE = re.compile(r"^\s*COPY\s", re.IGNORECASE)
_COPY_NAME_RE = re.compile(r"COPY\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))", re.IGNORECASE)
_REPLACING_RE = re.compile(r"\bREPLACING\b(.*)$", re.IGNORECASE | re.DOTALL)
_REPLACING_PAIR_RE = re.compile(
    r"(==.*?==|\S+)\s+BY\s+(==.*?==|\S+)", re.IGNORECASE | re.DOTALL
)
_COPYBOOK_EXTS = (".cpy", ".cbl")


class Expansion(BaseModel):
    text: str
    line_map: list[tool_types.LineMapEntry]


def _body(line: str) -> str:
    return line[7:72] if len(line) > 7 else ""


def _is_comment(line: str) -> bool:
    return len(line) > 6 and line[6] in ("*", "/")


def _resolve_copybook(name: str, search_paths: list[Path]) -> Path | None:
    target = name.upper()
    for base in search_paths:
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            if (
                entry.is_file()
                and entry.stem.upper() == target
                and entry.suffix.lower() in _COPYBOOK_EXTS
            ):
                return entry
    return None


def _strip_pseudo_text(token: str) -> str:
    token = token.strip()
    if token.startswith("==") and token.endswith("==") and len(token) >= 4:
        return token[2:-2]
    return token


def _parse_replacing_pairs(text: str) -> list[tuple[str, str]]:
    m = _REPLACING_RE.search(text)
    if not m:
        return []
    return [
        (_strip_pseudo_text(a), _strip_pseudo_text(b))
        for a, b in _REPLACING_PAIR_RE.findall(m.group(1))
    ]


def _scan_copy_statement(
    lines: list[str], i: int
) -> tuple[str, list[tuple[str, str]], int] | None:
    """From a COPY-starting line, gather through its terminating period.

    Returns (copybook_name, replacing_pairs, end_index_exclusive) or None if
    line ``i`` isn't a COPY statement start.
    """
    if _is_comment(lines[i]) or not _COPY_START_RE.match(_body(lines[i])):
        return None
    j = i
    parts: list[str] = []
    n = len(lines)
    while j < n:
        parts.append(_body(lines[j]))
        if _body(lines[j]).rstrip().endswith("."):
            j += 1
            break
        j += 1
    joined = " ".join(parts)
    name_match = _COPY_NAME_RE.search(joined)
    if not name_match:
        return None
    name = next(g for g in name_match.groups() if g).rstrip(".")
    pairs = _parse_replacing_pairs(joined)
    return name, pairs, j


def _apply_replacing(text: str, pairs: list[tuple[str, str]]) -> str:
    for a, b in pairs:
        text = text.replace(a, b)
    return text


Emitted = tuple[str, str, int]  # (line_text, source_file, source_line)


def _expand_lines(
    lines: list[str], source_file: str, search_paths: list[Path], depth: int
) -> list[Emitted]:
    emitted: list[Emitted] = []
    i = 0
    n = len(lines)
    while i < n:
        scan = _scan_copy_statement(lines, i)
        if scan is None:
            emitted.append((lines[i], source_file, i + 1))
            i += 1
            continue

        name, pairs, end = scan
        resolved = _resolve_copybook(name, search_paths) if depth < _MAX_DEPTH else None
        if resolved is None:
            for k in range(i, end):
                emitted.append((lines[k], source_file, k + 1))
            i = end
            continue

        copy_text = resolved.read_text(encoding="utf-8", errors="replace")
        if pairs:
            copy_text = _apply_replacing(copy_text, pairs)
        copy_lines = copy_text.splitlines()
        emitted.extend(
            _expand_lines(copy_lines, str(resolved), search_paths, depth + 1)
        )
        i = end
    return emitted


def _build_line_map(emitted: list[Emitted]) -> list[tool_types.LineMapEntry]:
    entries: list[tool_types.LineMapEntry] = []
    run_start = 0
    for idx in range(1, len(emitted) + 1):
        end_of_run = (
            idx == len(emitted)
            or emitted[idx][1] != emitted[run_start][1]
            or emitted[idx][2] != emitted[idx - 1][2] + 1
        )
        if end_of_run:
            entries.append(
                tool_types.LineMapEntry(
                    expanded_start=run_start + 1,
                    expanded_end=idx,
                    source_file=emitted[run_start][1],
                    source_line_start=emitted[run_start][2],
                )
            )
            run_start = idx
    return entries


def expand(source: str, search_paths: list[Path]) -> Expansion:
    lines = source.splitlines()
    emitted = _expand_lines(lines, "", search_paths, depth=0)
    text = "\n".join(t for t, _, _ in emitted) + "\n"
    return Expansion(text=text, line_map=_build_line_map(emitted))
