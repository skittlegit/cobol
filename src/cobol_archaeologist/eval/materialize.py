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
        raise MaterializationError("mutation provenance lacks parseable old/new") from exc
    if not isinstance(old, str) or not isinstance(new, str):
        raise MaterializationError("mutation old/new values must be strings")
    return old, new


def _hash_files(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(content.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def materialize(
    instance: DriftInstance,
    *,
    programs_root: Path = PROGRAMS,
) -> MaterializedSource:
    main = _find_unique(instance.provenance.base_program, programs_root)
    files = _load_source_closure(main)

    # Include explicitly named interprogram/copybook loci in the same source
    # bundle. This is source dispatch only; the system never sees gold loci.
    for locus in instance.code_locus.loci:
        if locus.file:
            name = Path(locus.file).name
        elif Path(locus.program).stem.upper() != main.stem.upper():
            name = (
                locus.program
                if Path(locus.program).suffix
                else f"{locus.program}.cbl"
            )
        else:
            continue
        if name not in files:
            path = main.parent / name
            if not path.is_file():
                path = _find_unique(name, programs_root)
            files[name] = path.read_text(encoding="utf-8", errors="replace")

    note = instance.provenance.mutation
    if instance.provenance.source == "synthetic" and note:
        old, new = _mutation_values(note)
        candidates: list[tuple[str, int]] = []
        for locus in instance.code_locus.loci:
            if locus.file:
                filename = Path(locus.file).name
            elif Path(locus.program).stem.upper() == main.stem.upper():
                filename = main.name
            else:
                filename = (
                    locus.program
                    if Path(locus.program).suffix
                    else f"{locus.program}.cbl"
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
        if not candidates and new == "(deleted)":
            # MO-2 provenance records the normalized multi-line statement while
            # the typed insertion-point locus names its final line. Match the
            # complete block, require it to cover a recorded locus, and blank it
            # without removing newlines so original-source line numbers survive.
            pattern = re.compile(
                r"\s+".join(re.escape(part) for part in old.split()),
                re.IGNORECASE,
            )
            block_matches: list[tuple[str, re.Match[str]]] = []
            for filename, text in files.items():
                for match in pattern.finditer(text):
                    start_line = text.count("\n", 0, match.start()) + 1
                    end_line = text.count("\n", 0, match.end()) + 1
                    if any(
                        (
                            Path(locus.file).name
                            if locus.file
                            else (
                                main.name
                                if Path(locus.program).stem.upper()
                                == main.stem.upper()
                                else (
                                    locus.program
                                    if Path(locus.program).suffix
                                    else f"{locus.program}.cbl"
                                )
                            )
                        )
                        == filename
                        and not (
                            locus.line_span[1] < start_line
                            or locus.line_span[0] > end_line
                        )
                        for locus in instance.code_locus.loci
                    ):
                        block_matches.append((filename, match))
            if len(block_matches) == 1:
                filename, match = block_matches[0]
                text = files[filename]
                blanked = "".join(
                    char if char in "\r\n" else " " for char in match.group()
                )
                files[filename] = (
                    text[: match.start()] + blanked + text[match.end() :]
                )
                return MaterializedSource(
                    main_file=main.name,
                    files=files,
                    source_sha256=_hash_files(files),
                )
        if not candidates:
            raise MaterializationError(
                f"recorded edit {old!r} matched {len(candidates)} locus lines"
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
                    raise MaterializationError("mutation replacement postcondition failed")
            files[filename] = "".join(lines)

    return MaterializedSource(
        main_file=main.name,
        files=files,
        source_sha256=_hash_files(files),
    )
