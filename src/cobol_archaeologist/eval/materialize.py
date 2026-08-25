"""Fail-closed reconstruction of benchmark source for real-tool evaluation."""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[3]
PROGRAMS = ROOT / "data" / "benchmark" / "seed" / "programs"
CORPORA = ROOT / "data" / "corpora"
_SOURCE_SUFFIXES = {".cbl", ".cob", ".cpy"}
_PROGRAM_ID_RE = re.compile(
    r"\bPROGRAM-ID\.\s+([A-Z0-9-]+)\.", re.IGNORECASE
)


class MaterializationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterializedSource:
    main_file: str
    files: dict[str, str]
    source_sha256: str

    def write_to(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name, content in self.files.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


def _find_unique(name: str, programs_root: Path) -> Path:
    matches = [
        path
        for path in programs_root.rglob(name)
        if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES
    ]
    if not matches and programs_root.resolve() == PROGRAMS.resolve():
        matches = [
            path
            for path in CORPORA.rglob(name)
            if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES
        ]
    if len(matches) != 1:
        raise MaterializationError(
            f"source {name!r} resolved to {len(matches)} paths: {matches}"
        )
    return matches[0]


def _copy_names(text: str) -> list[str]:
    return re.findall(
        r"^\s*COPY\s+([A-Z0-9_-]+)\s*\.",
        text,
        re.IGNORECASE | re.MULTILINE,
    )


def _load_source_closure(main: Path) -> dict[str, str]:
    files = {main.name: main.read_text(encoding="utf-8", errors="replace")}
    pending = list(_copy_names(files[main.name]))
    while pending:
        name = pending.pop()
        candidate = main.parent / f"{name}.cpy"
        if not candidate.is_file():
            candidate = _find_unique(candidate.name, PROGRAMS)
        if candidate.name in files:
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        files[candidate.name] = text
        pending.extend(_copy_names(text))
    return files


def _declared_programs(text: str) -> set[str]:
    return {match.group(1).upper() for match in _PROGRAM_ID_RE.finditer(text)}


def _locus_filename(*, locus, main: Path, main_programs: set[str]) -> str:
    if locus.file:
        return Path(locus.file).name
    program = Path(locus.program).stem.upper()
    if program == main.stem.upper() or program in main_programs:
        return main.name
    return locus.program if Path(locus.program).suffix else f"{locus.program}.cbl"


def _mutation_values(note: str) -> tuple[str, str]:
    fields: dict[str, str] = {}
    for segment in note.split(";")[1:]:
        key, separator, value = segment.strip().partition("=")
        if separator:
            fields[key] = value
    try:
        old = ast.literal_eval(fields["old"])
        new = ast.literal_eval(fields["new"])
    except (KeyError, SyntaxError, ValueError) as exc:
        raise MaterializationError(
            "mutation provenance lacks parseable old/new"
        ) from exc
    if not isinstance(old, str) or not isinstance(new, str):
        raise MaterializationError("mutation old/new values must be strings")
    return old, new


def _normalized_block_pattern(old: str) -> re.Pattern[str]:
    """Compile a case-insensitive pattern whose whitespace is insignificant."""

    parts = old.split()
    if not parts:
        raise MaterializationError("mutation provenance old value is empty")
    return re.compile(r"\s+".join(re.escape(part) for part in parts), re.IGNORECASE)


def _newline_sequences(text: str) -> list[str]:
    return re.findall(r"\r\n|\r|\n", text)


def _line_coordinate_replacement(original: str, replacement: str) -> str:
    """Keep a block replacement on the same source-line coordinate grid."""

    original_newlines = _newline_sequences(original)
    replacement_newlines = _newline_sequences(replacement)
    if len(replacement_newlines) > len(original_newlines):
        raise MaterializationError(
            "mutation replacement would add source lines and invalidate loci"
        )
    newline = original_newlines[0] if original_newlines else "\n"
    normalized = replacement.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", newline)
    return normalized + newline * (
        len(original_newlines) - len(replacement_newlines)
    )


def _blank_block(original: str) -> str:
    """Blank a deleted block while retaining every original newline."""

    return "".join(char if char in "\r\n" else " " for char in original)


def _find_normalized_block_matches(
    *,
    old: str,
    files: dict[str, str],
    loci,
    main: Path,
    main_programs: set[str],
) -> list[tuple[str, re.Match[str]]]:
    """Find unique provenance blocks only in their locus-resolved files."""

    pattern = _normalized_block_pattern(old)
    matches: list[tuple[str, re.Match[str]]] = []
    seen: set[tuple[str, int, int]] = set()
    for locus in loci:
        filename = _locus_filename(
            locus=locus, main=main, main_programs=main_programs
        )
        text = files.get(filename)
        if text is None:
            continue
        for match in pattern.finditer(text):
            start_line = text.count("\n", 0, match.start()) + 1
            end_line = text.count("\n", 0, match.end()) + 1
            if (
                locus.line_span[1] < start_line
                or locus.line_span[0] > end_line
            ):
                continue
            key = (filename, match.start(), match.end())
            if key not in seen:
                seen.add(key)
                matches.append((filename, match))
    return matches


def _hash_files(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(content.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def materialize_base(
    instance: DriftInstance,
    *,
    programs_root: Path = PROGRAMS,
) -> MaterializedSource:
    """Reconstruct the published base bundle without applying mutation metadata."""

    main = _find_unique(instance.provenance.base_program, programs_root)
    files = _load_source_closure(main)
    main_programs = _declared_programs(files[main.name])

    # Include explicitly named interprogram/copybook loci in the same source
    # bundle. This is source dispatch only; the system never sees gold loci.
    for locus in instance.code_locus.loci:
        name = _locus_filename(
            locus=locus, main=main, main_programs=main_programs
        )
        if name == main.name:
            continue
        if name not in files:
            path = main.parent / name
            if not path.is_file():
                path = _find_unique(name, programs_root)
            files[name] = path.read_text(encoding="utf-8", errors="replace")

    return MaterializedSource(
        main_file=main.name,
        files=files,
        source_sha256=_hash_files(files),
    )


def materialize(
    instance: DriftInstance,
    *,
    programs_root: Path = PROGRAMS,
) -> MaterializedSource:
    base = materialize_base(instance, programs_root=programs_root)
    main = _find_unique(instance.provenance.base_program, programs_root)
    files = dict(base.files)
    main_programs = _declared_programs(files[main.name])
    note = instance.provenance.mutation
    if instance.provenance.source == "synthetic" and note:
        old, new = _mutation_values(note)
        candidates: list[tuple[str, int]] = []
        for locus in instance.code_locus.loci:
            filename = _locus_filename(
                locus=locus, main=main, main_programs=main_programs
            )
            text = files.get(filename)
            if text is None:
                continue
            lines = text.splitlines(keepends=True)
            start, end = locus.line_span
            for index in range(start - 1, min(end, len(lines))):
                if old in lines[index]:
                    candidates.append((filename, index))
        candidates = sorted(set(candidates))
        block_matches = _find_normalized_block_matches(
            old=old,
            files=files,
            loci=instance.code_locus.loci,
            main=main,
            main_programs=main_programs,
        )
        multiline_matches = [
            (filename, match)
            for filename, match in block_matches
            if _newline_sequences(match.group())
        ]
        if not candidates or multiline_matches:
            if len(block_matches) != 1:
                raise MaterializationError(
                    f"normalized block {old!r} matched {len(block_matches)} "
                    "locus-overlapping blocks"
                )
            filename, match = block_matches[0]
            text = files[filename]
            replacement = (
                _blank_block(match.group())
                if new == "(deleted)"
                else _line_coordinate_replacement(match.group(), new)
            )
            files[filename] = text[: match.start()] + replacement + text[match.end() :]
            if files[filename].count("\n") != text.count("\n"):
                raise MaterializationError(
                    "mutation replacement changed the source line coordinate grid"
                )
            return MaterializedSource(
                main_file=main.name,
                files=files,
                source_sha256=_hash_files(files),
            )
        replacement = "" if new == "(deleted)" else new
        by_file: dict[str, list[int]] = {}
        for filename, index in candidates:
            by_file.setdefault(filename, []).append(index)
        for filename, indices in by_file.items():
            lines = files[filename].splitlines(keepends=True)
            for index in indices:
                if lines[index].count(old) != 1:
                    raise MaterializationError(
                        f"recorded edit {old!r} is ambiguous on {filename}:{index + 1}"
                    )
                lines[index] = lines[index].replace(old, replacement, 1)
                if replacement and replacement not in lines[index]:
                    raise MaterializationError(
                        "mutation replacement postcondition failed"
                    )
            files[filename] = "".join(lines)

    return MaterializedSource(
        main_file=main.name,
        files=files,
        source_sha256=_hash_files(files),
    )
