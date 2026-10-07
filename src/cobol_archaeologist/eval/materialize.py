"""The exact source a detector sees for a benchmark row."""

from __future__ import annotations

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
    """Return the exact program a detector sees for ``instance``.

    Real-curated rows are their base files. A synthetic row is its base files
    plus its stored edit (``data/benchmark/edits/<instance_id>.diff``).
    """

    base = materialize_base(instance, programs_root=programs_root)
    if instance.provenance.source != "synthetic":
        return base
    from cobol_archaeologist.benchmark.edits import apply_edit, edit_path

    path = edit_path(instance.instance_id)
    if not path.exists():
        raise MaterializationError(f"no stored edit for {instance.instance_id}")
    files = dict(base.files)
    main = _find_unique(instance.provenance.base_program, programs_root)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("--- a/"):
            name = line[len("--- a/") :].strip()
            if name not in files:
                sibling = main.parent / name
                source = sibling if sibling.is_file() else _find_unique(name, programs_root)
                files[name] = source.read_text(encoding="utf-8", errors="replace")
    try:
        files = apply_edit(instance.instance_id, files)
    except ValueError as exc:
        raise MaterializationError(f"{instance.instance_id}: {exc}") from exc
    return MaterializedSource(
        main_file=main.name,
        files=files,
        source_sha256=_hash_files(files),
    )
