"""T2.2 deterministic COBOL mutation operators and validation ladder."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from cobol_archaeologist.benchmark.surface import (
    SurfaceEdit,
    diversify_with_edits,
    perturb_nonregulated_literal,
)
from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.model.run_cobol import compile_check
from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.schemas import (
    CodeLocus,
    DriftInstance,
    Labels,
    Provenance,
    RegulationClause,
    SourceLineRef,
    SourceLocus,
    resolve_path,
)
from cobol_archaeologist.static_analysis.call_graph import build_call_graph
from cobol_archaeologist.static_analysis.slicer import slice_on


ValidationLevel = Literal["compiled", "syntax", "ast"]
ProgramKind = Literal["native", "cics"]

_OP_TO_DRIFT = {
    "MO-0": "D7_conformant",
    "MO-1": "D1_stale_threshold",
    "MO-2": "D2_missing_rule",
    "MO-3": "D3_contradictory",
    "MO-4": "D4_stale_reference_data",
    "MO-5": "D5_boundary_error",
    "MO-6": "D6_dead_code",
    "MO-1×": "D1_stale_threshold",
    "MO-3×": "D3_contradictory",
    "MO-6×": "D6_dead_code",
}
_HEADER_RE = re.compile(r"^\s{7}([A-Z0-9][A-Z0-9-]*)\.\s*$", re.IGNORECASE)
_PROGRAM_ID_RE = re.compile(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", re.IGNORECASE)
_VARIABLE_RE = re.compile(r"\b(?:WS|LK)-[A-Z0-9-]+\b", re.IGNORECASE)
_COMPARATOR_RE = re.compile(r"(?<![<>=])(?:>=|<=|>|<|=)(?![<>=])")


class MutationRejected(RuntimeError):
    """Raised when targeting or either validation pass rejects a mutation."""


@dataclass(frozen=True)
class ClauseRecord:
    record_id: str
    clause: RegulationClause
    check: dict


@dataclass(frozen=True)
class ProgramSource:
    program: str
    filename: str
    text: str
    kind: ProgramKind = "native"
    files: dict[str, str] = field(default_factory=dict)
    touched_variables: tuple[str, ...] = ()
    target_path: str | None = None

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        kind: ProgramKind = "native",
        files: dict[str, str] | None = None,
        touched_variables: tuple[str, ...] = (),
        target_path: str | None = None,
    ) -> "ProgramSource":
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8", errors="replace")
        discovered_files = dict(files or {})
        for copy_name in re.findall(
            r"^\s*COPY\s+([A-Z0-9_-]+)\s*\.", text, re.IGNORECASE | re.MULTILINE
        ):
            candidate = source_path.parent / f"{copy_name}.cpy"
            if candidate.is_file():
                discovered_files[candidate.name] = candidate.read_text(
                    encoding="utf-8", errors="replace"
                )
        return cls(
            program=_program_id(text, fallback=source_path.stem),
            filename=source_path.name,
            text=text,
            kind=kind,
            files=discovered_files,
            touched_variables=touched_variables,
            target_path=target_path,
        )


@dataclass(frozen=True)
class ValidationBlock:
    level: ValidationLevel
    ok: bool
    messages: tuple[str, ...] = ()
    pre_diversification_ok: bool = True


@dataclass(frozen=True)
class MutationResult:
    source: ProgramSource
    instance: DriftInstance
    validation: ValidationBlock
    surface_edits: tuple[SurfaceEdit, ...]

    def to_json(self) -> str:
        payload = {
            "source": {
                "program": self.source.program,
                "filename": self.source.filename,
                "text": self.source.text,
                "kind": self.source.kind,
                "files": dict(sorted(self.source.files.items())),
                "touched_variables": list(self.source.touched_variables),
                "target_path": self.source.target_path,
            },
            "instance": self.instance.model_dump(mode="json"),
            "validation": asdict(self.validation),
            "surface_edits": [asdict(edit) for edit in self.surface_edits],
        }
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


@dataclass(frozen=True)
class HostedSeed:
    record_id: str
    program: str
    operators: tuple[str, ...]


@dataclass(frozen=True)
class SeedMutationPlan:
    hosted: tuple[HostedSeed, ...]
    skipped_synthetic_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Touch:
    program: str
    file: str | None
    line_start: int
    line_end: int
    label: bool = True


@dataclass(frozen=True)
class _EditPlan:
    source: ProgramSource
    touches: tuple[_Touch, ...]
    old: str
    new: str
    slice_candidates: tuple[str, ...]
    surface_edits: tuple[SurfaceEdit, ...] = ()


def load_clause_records(path: str | Path) -> list[ClauseRecord]:
    records: list[ClauseRecord] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        try:
            clause = RegulationClause.model_validate(raw["clause"])
        except Exception as exc:  # pragma: no cover - diagnostic boundary
            raise ValueError(f"clause line {line_number} failed frozen schema") from exc
        records.append(
            ClauseRecord(
                record_id=str(raw["record_id"]),
                clause=clause,
                check=dict(raw["check"]),
            )
        )
    return records


def seed_mutation_plan(
    records: list[ClauseRecord],
    programs_dir: str | Path,
    instances_path: str | Path,
) -> SeedMutationPlan:
    """Match current D7 seed instances to synthetic-locus clause records."""

    programs_dir = Path(programs_dir)
    conformant: dict[tuple[str, str], set[str]] = {}
    for line in Path(instances_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        instance = DriftInstance.model_validate_json(line)
        if instance.drift_type != "D7_conformant":
            continue
        key = (instance.regulation_clause.doc, instance.regulation_clause.clause_id)
        if (programs_dir / instance.provenance.base_program).is_file():
            conformant.setdefault(key, set()).add(instance.provenance.base_program)

    hosted: list[HostedSeed] = []
    skipped: list[str] = []
    for record in records:
        if record.check.get("candidate_locus", {}).get("kind") != "synthetic":
            continue
        key = (record.clause.doc, record.clause.clause_id)
        programs = sorted(conformant.get(key, set()))
        if not programs:
            skipped.append(record.record_id)
            continue
        for program in programs:
            hosted.append(
                HostedSeed(
                    record_id=record.record_id,
                    program=program,
                    operators=tuple(record.check.get("mutation_ops", ())),
                )
            )
    return SeedMutationPlan(
        hosted=tuple(sorted(hosted, key=lambda item: (item.record_id, item.program))),
        skipped_synthetic_record_ids=tuple(sorted(skipped)),
    )


def _program_id(source: str, fallback: str) -> str:
    match = _PROGRAM_ID_RE.search(source)
    return match.group(1).upper() if match else fallback.upper()


def _join_like(source: str, lines: list[str]) -> str:
    ending = "\n" if source.endswith(("\n", "\r")) else ""
    return "\n".join(lines) + ending


def _procedure_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if re.search(r"\bPROCEDURE\s+DIVISION\b", line, re.IGNORECASE):
            return index
    raise MutationRejected("source has no PROCEDURE DIVISION")


def _paragraph_spans(source: str) -> list[tuple[str, int, int]]:
    lines = source.splitlines()
    procedure = _procedure_index(lines)
    starts = [
        (match.group(1).upper(), index + 1)
        for index, line in enumerate(lines[procedure + 1 :], procedure + 1)
        if (match := _HEADER_RE.match(line))
    ]
    spans: list[tuple[str, int, int]] = []
    for index, (name, start) in enumerate(starts):
        end = starts[index + 1][1] - 1 if index + 1 < len(starts) else len(lines)
        spans.append((name, start, end))
    return spans


def _paragraph_for(source: str, line: int) -> str | None:
    return next(
        (name for name, start, end in _paragraph_spans(source) if start <= line <= end),
        None,
    )


def _variables(line: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(match.group(0).upper() for match in _VARIABLE_RE.finditer(line))
    )


def _replace_line(source: str, index: int, new_line: str) -> str:
    lines = source.splitlines()
    lines[index] = new_line
    return _join_like(source, lines)


def _format_number_like(old_text: str, value: float) -> str:
    if "." in old_text:
        decimals = len(old_text.split(".", 1)[1])
        return f"{value:.{decimals}f}"
    return str(int(value)) if float(value).is_integer() else str(value)


def _numeric_occurrence(source: str, value: float) -> tuple[int, re.Match[str]]:
    lines = source.splitlines()
    integer = int(value)
    if float(value).is_integer():
        pattern = re.compile(rf"(?<![\d.]){integer}(?:\.0+)?(?!\d)")
    else:
        pattern = re.compile(rf"(?<![\d.]){re.escape(str(value))}(?!\d)")
    candidates: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        if len(line) > 6 and line[6] in "*/":
            continue
        candidates.extend((index, match) for match in pattern.finditer(line))
    if not candidates:
        raise MutationRejected(f"current value {value!r} not found in source")
    return next(
        (
            candidate
            for candidate in candidates
            if "VALUE" in lines[candidate[0]].upper()
        ),
        candidates[0],
    )


def _flatten_value(value, prefix: str = "") -> list[tuple[str | None, object]]:
    if isinstance(value, BaseModel) and hasattr(value, "value"):
        node_value = value.value
    elif isinstance(value, dict) and "kind" in value and "value" in value:
        node_value = value["value"]
    else:
        node_value = value
    if isinstance(node_value, dict):
        flattened: list[tuple[str | None, object]] = []
        for name, child in node_value.items():
            child_prefix = f"{prefix}.{name}" if prefix else name
            flattened.extend(_flatten_value(child, child_prefix))
        return flattened
    return [(prefix or None, node_value)]


def _target_leaf(
    base: ProgramSource, record: ClauseRecord
) -> tuple[str | None, object]:
    current = record.clause.current_value
    if current is None:
        raise MutationRejected(f"{record.record_id} has no current_value")
    if base.target_path is not None:
        return base.target_path, resolve_path(current, base.target_path).value
    leaves = _flatten_value(current)
    for path, value in leaves:
        if isinstance(value, (int, float)):
            try:
                _numeric_occurrence(base.text, float(value))
            except MutationRejected:
                continue
            return path, value
    return leaves[0]


def _raw_scalars(value) -> list[object]:
    if isinstance(value, dict):
        if "kind" in value and "value" in value:
            return _raw_scalars(value["value"])
        values: list[object] = []
        for child in value.values():
            values.extend(_raw_scalars(child))
        return values
    if isinstance(value, list):
        values: list[object] = []
        for child in value:
            values.extend(_raw_scalars(child))
        return values
    return [value]


def _stale_value(record: ClauseRecord, current: float, rng: random.Random) -> float:
    candidates: list[float] = []
    for key in ("prior_versions", "prior_2022"):
        raw = record.check.get(key, [])
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            for value in _raw_scalars(
                item.get("value", {}) if isinstance(item, dict) else {}
            ):
                if isinstance(value, (int, float)) and float(value) != current:
                    candidates.append(float(value))
    if candidates:
        return candidates[rng.randrange(len(candidates))]
    delta = max(1.0, round(abs(current) * 0.1))
    return current + delta


def _apply_mo0(
    base: ProgramSource, record: ClauseRecord, rng: random.Random
) -> _EditPlan:
    protected = (
        {str(value) for _, value in _flatten_value(record.clause.current_value)}
        if record.clause.current_value
        else set()
    )
    text, edits = perturb_nonregulated_literal(base.text, protected, rng)
    if not edits:
        text, edits = diversify_with_edits(base.text, None, rng)
    if not edits:
        raise MutationRejected("MO-0 found no benign edit target")
    edit = edits[0]
    variables = _variables(edit.new) or base.touched_variables
    return _EditPlan(
        source=replace(base, text=text),
        touches=(_Touch(base.program, None, edit.line, edit.line),),
        old=edit.old.strip(),
        new=edit.new.strip(),
        slice_candidates=tuple(variables),
        surface_edits=edits,
    )


def _apply_mo1(
    base: ProgramSource, record: ClauseRecord, rng: random.Random
) -> _EditPlan:
    _, raw_current = _target_leaf(base, record)
    if not isinstance(raw_current, (int, float)):
        raise MutationRejected("MO-1 requires a numeric current_value leaf")
    current = float(raw_current)
    stale = _stale_value(record, current, rng)
    index, match = _numeric_occurrence(base.text, current)
    lines = base.text.splitlines()
    old_line = lines[index]
    replacement = _format_number_like(match.group(0), stale)
    lines[index] = old_line[: match.start()] + replacement + old_line[match.end() :]
    variables = _variables(lines[index]) or base.touched_variables
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(_Touch(base.program, None, index + 1, index + 1),),
        old=match.group(0),
        new=replacement,
        slice_candidates=tuple(variables),
    )


def _if_block(
    lines: list[str], preferred_variables: tuple[str, ...]
) -> tuple[int, int]:
    procedure = _procedure_index(lines)
    candidates = [
        index
        for index in range(procedure + 1, len(lines))
        if re.search(r"\bIF\b", lines[index], re.IGNORECASE)
    ]
    preferred = [
        index
        for index in candidates
        if any(
            variable.upper() in lines[index].upper() for variable in preferred_variables
        )
    ]
    if not (preferred or candidates):
        raise MutationRejected("no IF block found")
    start = (preferred or candidates)[0]
    depth = 0
    for index in range(start, len(lines)):
        depth += len(re.findall(r"(?<!END-)\bIF\b", lines[index], re.IGNORECASE))
        depth -= len(re.findall(r"\bEND-IF\b", lines[index], re.IGNORECASE))
        if index > start and depth <= 0:
            return start, index
    raise MutationRejected("IF block has no END-IF")


def _apply_mo2(base: ProgramSource) -> _EditPlan:
    lines = base.text.splitlines()
    start, end = _if_block(lines, base.touched_variables)
    old = " ".join(line.strip() for line in lines[start : end + 1])
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    lines[start] = f"{indent}CONTINUE."
    for index in range(start + 1, end + 1):
        lines[index] = ""
    variables = _variables(old) or base.touched_variables
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(_Touch(base.program, None, start + 1, end + 1),),
        old=old,
        new="CONTINUE (required check removed)",
        slice_candidates=tuple(variables),
    )


def _comparator_edit(
    base: ProgramSource,
    replacements: dict[str, str],
    preferred_value: object | None = None,
) -> _EditPlan:
    lines = base.text.splitlines()
    procedure = _procedure_index(lines)
    candidates: list[tuple[int, re.Match[str]]] = []
    for index in range(procedure + 1, len(lines)):
        if not re.search(r"\bIF\b", lines[index], re.IGNORECASE):
            continue
        for match in _COMPARATOR_RE.finditer(lines[index]):
            if match.group(0) in replacements:
                candidates.append((index, match))
    if preferred_value is not None:
        preferred = [
            item for item in candidates if str(preferred_value) in lines[item[0]]
        ]
        if preferred:
            candidates = preferred
    if not candidates:
        raise MutationRejected("no mutable comparator found")
    index, match = candidates[0]
    old = match.group(0)
    new = replacements[old]
    lines[index] = lines[index][: match.start()] + new + lines[index][match.end() :]
    variables = _variables(lines[index]) or base.touched_variables
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(_Touch(base.program, None, index + 1, index + 1),),
        old=old,
        new=new,
        slice_candidates=tuple(variables),
    )


def _apply_mo4(base: ProgramSource, rng: random.Random) -> _EditPlan:
    candidates = sorted(
        name for name in base.files if name.lower().endswith((".cpy", ".cob"))
    )
    for name in candidates:
        lines = base.files[name].splitlines()
        for index, line in enumerate(lines):
            if "88 " not in line.upper() or "VALUE" not in line.upper():
                continue
            literals = list(re.finditer(r"'([^']+)'", line))
            if not literals:
                continue
            match = literals[rng.randrange(len(literals))]
            old = match.group(1)
            new = "Z" * len(old)
            lines[index] = line[: match.start(1)] + new + line[match.end(1) :]
            files = dict(base.files)
            files[name] = _join_like(base.files[name], lines)
            condition = re.search(r"\b88\s+([A-Z0-9-]+)", line, re.IGNORECASE)
            variables = (
                (
                    condition.group(1).upper(),
                    *base.touched_variables,
                    *_variables(base.text),
                )
                if condition
                else base.touched_variables
            )
            return _EditPlan(
                source=replace(base, files=files),
                touches=(_Touch(base.program, name, index + 1, index + 1),),
                old=old,
                new=new,
                slice_candidates=tuple(variables),
            )
    raise MutationRejected("MO-4 requires an 88-level VALUES list in a copybook")


def _apply_mo6(base: ProgramSource) -> _EditPlan:
    lines = base.text.splitlines()
    start, end = _if_block(lines, base.touched_variables)
    original = " ".join(line.strip() for line in lines[start : end + 1])
    procedure = _procedure_index(lines)
    declaration = "       01  WS-COMPLIANCE-FLAG PIC X VALUE 'N'."
    lines.insert(procedure, declaration)
    start += 1
    end += 1
    lines[end] = re.sub(r"\.\s*$", "", lines[end])
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    lines.insert(start, f"{indent}IF WS-COMPLIANCE-FLAG = 'Y'")
    lines.insert(end + 2, f"{indent}END-IF.")
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(_Touch(base.program, None, start + 1, end + 3),),
        old=original,
        new="always-false WS-COMPLIANCE-FLAG guard",
        slice_candidates=("WS-COMPLIANCE-FLAG",),
    )


def _apply_mo1x(base: ProgramSource) -> _EditPlan:
    copybooks = sorted(
        name for name in base.files if name.lower().endswith((".cpy", ".cob"))
    )
    for name in copybooks:
        lines = base.files[name].splitlines()
        candidates: list[tuple[int, re.Match[str]]] = []
        for index, line in enumerate(lines):
            value_match = re.search(r"\bVALUE\s+(.+?)(?:\.\s*)?$", line, re.IGNORECASE)
            if "CUTOFF" not in line.upper() or value_match is None:
                continue
            candidates.extend(
                (index, match)
                for match in re.finditer(r"(?<![.\d])\d{2,}(?!\d)", line)
                if match.start() >= value_match.start(1)
            )
        if candidates:
            index, match = max(candidates, key=lambda item: int(item[1].group(0)))
            line = lines[index]
            old = match.group(0)
            new = str(int(old) + max(100, int(old) // 5))
            lines[index] = line[: match.start()] + new + line[match.end() :]
            files = dict(base.files)
            files[name] = _join_like(base.files[name], lines)
            variable = next(iter(_variables(line)), "WS-CUTOFF-AMOUNT")
            main_lines = base.text.splitlines()
            use_index = next(
                (
                    i
                    for i, main_line in enumerate(main_lines)
                    if variable in main_line.upper()
                ),
                None,
            )
            if use_index is None:
                raise MutationRejected(
                    f"copybook variable {variable} has no use in main source"
                )
            return _EditPlan(
                source=replace(base, files=files),
                touches=(
                    _Touch(base.program, name, index + 1, index + 1),
                    _Touch(
                        base.program, None, use_index + 1, use_index + 1, label=False
                    ),
                ),
                old=old,
                new=new,
                slice_candidates=(variable, *base.touched_variables),
            )
    raise MutationRejected("MO-1× requires a copybook cutoff constant")


def _apply_mo3x(base: ProgramSource) -> _EditPlan:
    lines = base.text.splitlines()
    gate_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"\bIF\s+WS-VALID\s*=\s*'Y'", line, re.IGNORECASE)
        ),
        None,
    )
    if gate_index is None:
        raise MutationRejected("MO-3× requires a validate-then-post gate")
    old_line = lines[gate_index]
    lines[gate_index] = re.sub(
        r"=\s*'Y'", "NOT = 'X'", old_line, count=1, flags=re.IGNORECASE
    )
    blocker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if index > gate_index
            and re.search(r"\bIF\s+WS-BALANCE\b", line, re.IGNORECASE)
        ),
        None,
    )
    if blocker_index is None:
        raise MutationRejected("MO-3× requires a separate blocking paragraph")
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(
            _Touch(base.program, None, gate_index + 1, gate_index + 1),
            _Touch(
                base.program, None, blocker_index + 1, blocker_index + 1, label=False
            ),
        ),
        old=old_line.strip(),
        new=lines[gate_index].strip(),
        slice_candidates=("WS-VALID", "WS-BALANCE"),
    )


def _apply_mo6x(base: ProgramSource) -> _EditPlan:
    related = sorted(
        name for name in base.files if name.lower().endswith((".cbl", ".cob"))
    )
    for name in related:
        lines = base.files[name].splitlines()
        for index, line in enumerate(lines):
            if (
                "COMPLIANCE-ENABLED" not in line.upper()
                or "VALUE 'Y'" not in line.upper()
            ):
                continue
            new_line = re.sub(
                r"VALUE\s+'Y'", "VALUE 'N'", line, count=1, flags=re.IGNORECASE
            )
            lines[index] = new_line
            files = dict(base.files)
            files[name] = _join_like(base.files[name], lines)
            related_program = _program_id(files[name], fallback=Path(name).stem)
            guard_index = next(
                (
                    i
                    for i, main_line in enumerate(base.text.splitlines())
                    if "LK-COMPLIANCE-ENABLED" in main_line.upper()
                    and "IF " in main_line.upper()
                ),
                None,
            )
            if guard_index is None:
                raise MutationRejected("MO-6× requires a guarded compliance subprogram")
            return _EditPlan(
                source=replace(base, files=files),
                touches=(
                    _Touch(related_program, name, index + 1, index + 1),
                    _Touch(
                        base.program,
                        None,
                        guard_index + 1,
                        guard_index + 1,
                        label=False,
                    ),
                ),
                old="VALUE 'Y'",
                new="VALUE 'N'",
                slice_candidates=(
                    "WS-COMPLIANCE-ENABLED",
                    "LK-COMPLIANCE-ENABLED",
                    *base.touched_variables,
                ),
            )
    raise MutationRejected("MO-6× requires a related program flag initialized to Y")


def _apply(
    base: ProgramSource, record: ClauseRecord, op: str, rng: random.Random
) -> _EditPlan:
    if op == "MO-0":
        return _apply_mo0(base, record, rng)
    if op == "MO-1":
        return _apply_mo1(base, record, rng)
    if op == "MO-2":
        return _apply_mo2(base)
    if op == "MO-3":
        return _comparator_edit(
            base, {">": "<=", ">=": "<", "<": ">=", "<=": ">", "=": "NOT ="}
        )
    if op == "MO-4":
        return _apply_mo4(base, rng)
    if op == "MO-5":
        _, current = _target_leaf(base, record)
        return _comparator_edit(
            base, {">": ">=", ">=": ">", "<": "<=", "<=": "<"}, current
        )
    if op == "MO-6":
        return _apply_mo6(base)
    if op == "MO-1×":
        return _apply_mo1x(base)
    if op == "MO-3×":
        return _apply_mo3x(base)
    if op == "MO-6×":
        return _apply_mo6x(base)
    raise ValueError(f"unknown mutation operator: {op}")


def _program_texts(source: ProgramSource, directory: Path) -> list[tuple[str, str]]:
    (directory / source.filename).write_text(source.text, encoding="utf-8")
    for name, text in source.files.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    programs = [(source.filename, source.text)] + [
        (name, text)
        for name, text in sorted(source.files.items())
        if name.lower().endswith((".cbl", ".cob"))
    ]
    expanded: list[tuple[str, str]] = []
    for name, text in programs:
        prepared = preprocess(text).text if source.kind == "cics" else text
        prepared = expand(prepared, [directory]).text
        expanded.append((name, prepared))
    return expanded


def _ast_ok(source: str) -> bool:
    from tree_sitter import Parser

    from cobol_archaeologist.parser._grammar import get_language

    parser = Parser()
    parser.set_language(get_language())
    tree = parser.parse(preprocess(source).text.encode("utf-8"))
    return not tree.root_node.has_error


def _validate(source: ProgramSource, baseline: ProgramSource) -> ValidationBlock:
    cobc_present = bool(os.environ.get("COBC") or shutil.which("cobc"))
    with tempfile.TemporaryDirectory(prefix="t22_validate_") as tmp:
        directory = Path(tmp)
        programs = _program_texts(source, directory)
        if cobc_present:
            level: ValidationLevel = "syntax" if source.kind == "cics" else "compiled"
            messages: list[str] = []
            ok = True
            for name, text in programs:
                result = compile_check(text)
                if not result.ok:
                    ok = False
                    messages.extend(f"{name}: {message}" for message in result.messages)
            return ValidationBlock(level=level, ok=ok, messages=tuple(messages))

        ok = all(_ast_ok(text) for _, text in programs)
        baseline_names = {
            name: tuple(paragraph for paragraph, _, _ in _paragraph_spans(text))
            for name, text in [
                (baseline.filename, baseline.text),
                *baseline.files.items(),
            ]
            if name.lower().endswith((".cbl", ".cob"))
        }
        mutated_names = {
            name: tuple(paragraph for paragraph, _, _ in _paragraph_spans(text))
            for name, text in [(source.filename, source.text), *source.files.items()]
            if name.lower().endswith((".cbl", ".cob"))
        }
        if baseline_names != mutated_names:
            ok = False
        messages = () if ok else ("AST ERROR node or paragraph-structure change",)
        return ValidationBlock(level="ast", ok=ok, messages=messages)


def _slice_evidence(
    source: ProgramSource,
    candidates: tuple[str, ...],
) -> tuple[tuple[str, ...], set[tuple[str, str]]]:
    with tempfile.TemporaryDirectory(prefix="t22_slice_") as tmp:
        directory = Path(tmp)
        (directory / source.filename).write_text(source.text, encoding="utf-8")
        for name, text in source.files.items():
            (directory / name).write_text(text, encoding="utf-8")
        program_paths = [directory / source.filename] + [
            directory / name
            for name in sorted(source.files)
            if name.lower().endswith((".cbl", ".cob"))
        ]
        programs = [
            parse_program(path, include_preamble=True) for path in program_paths
        ]
        preprocess_results = {
            program.program_id: preprocess(
                Path(program.path).read_text(encoding="utf-8")
            )
            for program in programs
        }
        graph = build_call_graph(programs, preprocess_results)
        found: list[str] = []
        spread: set[tuple[str, str]] = set()
        for candidate in dict.fromkeys(item.upper() for item in candidates if item):
            sliced = slice_on(candidate, programs, graph, program=None)
            if not sliced.statements:
                continue
            found.append(candidate)
            spread.update(
                (statement.ref.program, statement.ref.paragraph or "")
                for statement in sliced.statements
            )
        if not found:
            raise MutationRejected(
                f"slice_on found no evidence for touched variables {candidates!r}"
            )
        return tuple(found), spread


def _touch_source(source: ProgramSource, touch: _Touch) -> str:
    if touch.file is None:
        return source.text
    try:
        return source.files[touch.file]
    except KeyError as exc:
        raise MutationRejected(
            f"locus file {touch.file!r} missing from mutated source"
        ) from exc


def _loci(
    source: ProgramSource, touches: tuple[_Touch, ...]
) -> tuple[list[SourceLocus], list[SourceLineRef]]:
    loci: list[SourceLocus] = []
    labels: list[SourceLineRef] = []
    seen: set[tuple] = set()
    for touch in touches:
        text = _touch_source(source, touch)
        line_count = len(text.splitlines())
        if touch.line_start < 1 or touch.line_end > line_count:
            raise MutationRejected(f"touch {touch} falls outside mutated source")
        paragraph = (
            None
            if touch.file and touch.file.lower().endswith((".cpy", ".copy"))
            else _paragraph_for(text, touch.line_start)
        )
        key = (touch.program, touch.file, paragraph, touch.line_start, touch.line_end)
        if key not in seen:
            seen.add(key)
            loci.append(
                SourceLocus(
                    program=touch.program,
                    paragraph=paragraph,
                    file=touch.file,
                    line_span=(touch.line_start, touch.line_end),
                )
            )
        if touch.label:
            labels.append(
                SourceLineRef(
                    program=touch.program,
                    file=touch.file,
                    line=touch.line_start,
                )
            )
    loci.sort(key=lambda item: (item.program, item.file or "", item.line_span))
    labels.sort(key=lambda item: (item.program, item.file or "", item.line))
    return loci, labels


def _instance_id(source: ProgramSource, record: ClauseRecord, op: str) -> str:
    payload = json.dumps(
        {
            "program": source.program,
            "text": source.text,
            "files": source.files,
            "record": record.record_id,
            "op": op,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    number = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 1_000_000
    return f"drift_{number:06d}"


def _locus_description(loci: list[SourceLocus]) -> str:
    return "+".join(
        f"{locus.program}:{locus.file or locus.paragraph or '<source>'}:{locus.line_span[0]}-{locus.line_span[1]}"
        for locus in loci
    )


def mutate(
    base: ProgramSource,
    record: ClauseRecord,
    op: str,
    rng: random.Random,
) -> MutationResult:
    """Mutate one conformant COBOL source deterministically under ``rng``."""

    if op not in _OP_TO_DRIFT:
        raise ValueError(f"unknown mutation operator: {op}")
    legal = set(record.check.get("mutation_ops", ()))
    if op != "MO-0" and op not in legal:
        raise MutationRejected(
            f"{op} is not legal for clause record {record.record_id}"
        )

    surface_rng = random.Random(rng.getrandbits(64))
    plan = _apply(base, record, op, rng)
    pre_validation = _validate(plan.source, base)
    if not pre_validation.ok:
        raise MutationRejected(
            f"{op} failed {pre_validation.level} before diversification: "
            + "; ".join(pre_validation.messages)
        )

    semantic_lines = [touch for touch in plan.touches if touch.file is None]
    region = None
    if semantic_lines:
        region = (
            min(touch.line_start for touch in semantic_lines),
            max(touch.line_end for touch in semantic_lines),
        )
    diversified_text, diversification = diversify_with_edits(
        plan.source.text, region, surface_rng
    )
    diversified = replace(plan.source, text=diversified_text)
    validation = _validate(diversified, base)
    validation = replace(
        validation,
        pre_diversification_ok=pre_validation.ok,
    )
    if not validation.ok:
        raise MutationRejected(
            f"{op} failed {validation.level} after diversification: "
            + "; ".join(validation.messages)
        )

    slice_vars, slice_spread = _slice_evidence(diversified, plan.slice_candidates)
    is_cross = op.endswith("×")
    # DECISION: base operators label the local semantic edit even when the
    # backward slice includes a caller/ACCEPT paragraph. Cross variants must
    # additionally prove multi-paragraph/program slice spread before emission.
    if is_cross and len(slice_spread) < 2:
        raise MutationRejected(f"{op} did not produce interprocedural slice evidence")

    loci, line_labels = _loci(diversified, plan.touches)
    if (
        is_cross
        and len({(item.program, item.file, item.paragraph) for item in loci}) < 2
    ):
        raise MutationRejected(f"{op} requires at least two emitted loci")

    target_path = base.target_path
    current = record.clause.current_value
    drift_type = _OP_TO_DRIFT[op]
    if (
        current is not None
        and current.kind == "composite"
        and drift_type
        in {
            "D1_stale_threshold",
            "D5_boundary_error",
        }
    ):
        target_path = target_path or _target_leaf(base, record)[0]
    if target_path is not None and current is not None:
        resolve_path(current, target_path)

    if drift_type == "D7_conformant":
        line_labels = []
        program_label = paragraph_label = "conformant"
        rationale = (
            f"{op} applies only benign surface variation at {_locus_description(loci)}; "
            "the regulatory behavior is unchanged."
        )
    else:
        program_label = paragraph_label = "drift"
        rationale = (
            f"{op} changes {plan.old!r} to {plan.new!r} at "
            f"{_locus_description(loci)}, producing {drift_type}."
        )

    mutation_note = (
        f"{op}; locus={_locus_description(loci)}; old={plan.old!r}; "
        f"new={plan.new!r}; validation={validation.level}"
    )
    instance = DriftInstance(
        instance_id=_instance_id(diversified, record, op),
        regulation_clause=record.clause,
        code_locus=CodeLocus(
            loci=loci,
            slice_vars=list(slice_vars),
            is_interprocedural=is_cross,
        ),
        drift_type=drift_type,
        target_path=target_path,
        labels=Labels(
            program_level=program_label,
            paragraph_level=paragraph_label,
            line_level=line_labels,
        ),
        gold_rationale=rationale,
        provenance=Provenance(
            source="synthetic",
            base_program=diversified.filename,
            mutation=mutation_note,
            annotator_notes=None,
        ),
    )
    return MutationResult(
        source=diversified,
        instance=instance,
        validation=validation,
        surface_edits=plan.surface_edits + diversification,
    )
