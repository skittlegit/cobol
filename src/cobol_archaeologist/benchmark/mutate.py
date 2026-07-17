"""T2.2 deterministic COBOL mutation operators and validation ladder."""

from __future__ import annotations

import hashlib
import json
import math
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
_QUOTED_LITERAL_RE = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
_UNPAID_TERM_RE = re.compile(
    r"\s*-\s*((?:WS|LK)-[A-Z0-9-]*(?:UNPAID|FEE|CHARGE)[A-Z0-9-]*)\b", re.IGNORECASE
)


class MutationRejected(RuntimeError):
    """Raised when targeting or either validation pass rejects a mutation."""


class ClauseDataError(RuntimeError):
    """Raised when a clause record cannot support the operator it declares.

    Deliberately NOT a :class:`MutationRejected`: the build catches that one and
    counts it as ordinary yield loss, which is exactly how a data gap turns into
    silence. This propagates and fails the build.
    """


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
    stale_source: str | None = None


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


def _control_text(line: str) -> str:
    """Mask literals/comments while preserving token offsets for control parsing."""

    if len(line) > 6 and line[6] in "*/":
        return ""
    return _QUOTED_LITERAL_RE.sub(lambda match: " " * len(match.group(0)), line)


def _procedure_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if re.search(r"\bPROCEDURE\s+DIVISION\b", line, re.IGNORECASE):
            return index
    raise MutationRejected("source has no PROCEDURE DIVISION")


def _working_storage_end(lines: list[str], procedure: int) -> int:
    """Return the safe insertion point for a generated working-storage item."""

    return next(
        (
            index
            for index in range(procedure)
            if re.search(r"\bLINKAGE\s+SECTION\b", lines[index], re.IGNORECASE)
        ),
        procedure,
    )


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


def _numeric_pattern(value: float) -> re.Pattern[str]:
    if float(value).is_integer():
        return re.compile(rf"(?<![\d.]){int(value)}(?:\.0+)?(?!\d)")
    return re.compile(rf"(?<![\d.]){re.escape(str(value))}(?!\d)")


def _numeric_occurrence(
    source: str,
    value: float,
    preferred_variables: tuple[str, ...] = (),
) -> tuple[int, re.Match[str]]:
    lines = source.splitlines()
    pattern = _numeric_pattern(value)
    candidates: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        if len(line) > 6 and line[6] in "*/":
            continue
        candidates.extend((index, match) for match in pattern.finditer(line))
    if not candidates:
        raise MutationRejected(f"current value {value!r} not found in source")
    procedure = _procedure_index(lines)
    preferred = tuple(variable.upper() for variable in preferred_variables)
    conditional = next(
        (
            candidate
            for candidate in candidates
            if candidate[0] > procedure
            and re.search(r"\b(?:IF|WHEN)\b", lines[candidate[0]], re.IGNORECASE)
            and any(variable in lines[candidate[0]].upper() for variable in preferred)
        ),
        None,
    )
    if conditional is not None:
        return conditional
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
                _numeric_occurrence(base.text, float(value), base.touched_variables)
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


# T2.4b (BL-6 follow-on): plausible former values, per current_value kind.
# Regulators legislate on round windows, so an off-grid threshold is the tell --
# the retired ``current * 1.1`` fallback emitted a 33-day SLA no maintainer ever
# wrote. Each grid is the set of values that kind actually takes in the RBI
# lineage; the stale value is snapped onto it. Grids are keyed by kind (not by
# instance) so the choice stays deterministic and inspectable.
_STALE_GRIDS: dict[str, tuple[float, ...]] = {
    "duration_days": (7, 14, 15, 30, 45, 60, 90),
    "duration_working_days": (3, 7, 10),
    "duration_years": (1, 2, 5, 8, 10),
    "duration_months": (1, 2, 3, 6, 12),
    "percentage": (10, 15, 25),
}


def _round_amount(current: float, *, downward: bool) -> float:
    """Adjacent amount on the 1-2-5 decade ladder (500 -> 1000, or -> 200).

    Money thresholds move between round figures, never to 550. Direction is the
    caller's: a ceiling the bank must stay under was laxer when larger; a floor
    it must pay (a per-day penalty) was laxer when smaller.
    """

    exponent = math.floor(math.log10(abs(current))) if current else 0
    ladder = [
        float(mantissa * (10**power))
        for power in range(exponent - 1, exponent + 2)
        for mantissa in (1, 2, 5)
    ]
    side = [value for value in ladder if value < current] if downward else [
        value for value in ladder if value > current
    ]
    if not side:
        raise MutationRejected(f"no laxer round amount for {current}")
    return max(side) if downward else min(side)


# Stale drift is laxer *for the obligated party* -- an un-updated rule lets the
# bank do less than it currently must. Which numeric direction that is depends
# on what the clause's comparator makes the value: a ceiling the bank must stay
# under (SLA <= 30 days) is laxer when larger; a floor it must provide
# (notice >= 15 days) is laxer when smaller -- 7 days' notice is the customer
# getting less. Conflating the two holds for ceilings and inverts for floors.
_FLOOR_COMPARATORS = frozenset({"at_least"})


def _leaf_node(current, path: str | None):
    if current is None:
        return None
    if path is None:
        return current
    try:
        return resolve_path(current, path)
    except KeyError:
        return None


def _leaf_kind(current, path: str | None) -> str | None:
    node = _leaf_node(current, path)
    return node.kind if node is not None else None


def _is_floor(current, path: str | None, record_id: str = "<clause>") -> bool:
    """Is this leaf a floor (a minimum the obligated party must provide)?

    A missing comparator is a hard error, never a silent ceiling default. BL-15
    existed only because absence was interpretable: ``penalty_per_day`` is
    floor-shaped, declared nothing, and so drifted *up* to a stricter penalty --
    the opposite of drift -- with no gate able to see it. Absence must fail.
    """

    node = _leaf_node(current, path)
    if node is None:
        raise ClauseDataError(f"{record_id}: no current_value leaf at {path!r}")
    comparator = getattr(node, "comparator", None)
    if comparator is None:
        raise ClauseDataError(
            f"{record_id}: leaf {path or '<root>'} ({node.kind}) declares no "
            "comparator, so its stale side cannot be determined. Every leaf an "
            "operator can target must declare one explicitly (BL-15)."
        )
    return comparator in _FLOOR_COMPARATORS


def _assert_snap_direction(
    record: ClauseRecord, current: float, stale: float, is_floor: bool
) -> None:
    """Floor clauses never snap upward; ceiling clauses never snap downward.

    The snap direction is a conceptual claim about how drift accumulates, not an
    implementation detail, so it is asserted rather than merely implemented: a
    floor clause drifting *up* would encode the regulator having loosened
    consumer protection. The moment a second ``at_least`` clause enters the set
    this fails loudly instead of silently mislabelling its D1 instances.

    Only clauses that declare a ``comparator`` are protected -- a floor-shaped
    value with no recorded comparator reads as a ceiling here.
    """

    if is_floor and stale > current:
        raise MutationRejected(
            f"{record.record_id}: floor clause snapped up ({current} -> {stale}); "
            "a stale value must be laxer for the obligated party"
        )
    if not is_floor and stale < current:
        raise MutationRejected(
            f"{record.record_id}: ceiling clause snapped down ({current} -> {stale}); "
            "a stale value must be laxer for the obligated party"
        )


def _exact_wrong_value(
    record: ClauseRecord, current: float, rng: random.Random
) -> tuple[float, str]:
    """A fixed statutory constant has no laxer side -- only a wrong value.

    The 2x penalty on unsolicited-card charges is not a threshold with a window
    that slid: drift here is the constant itself being wrong. Selected via
    ``check.mo1_mode == "exact_wrong"``, so the clause declares that it is
    non-directional rather than the snap logic inferring it -- the inference
    hole BL-15 was. Candidates are declared too, never derived.
    """

    declared = record.check.get("mo1_wrong_values")
    if not isinstance(declared, list) or not declared:
        raise ClauseDataError(
            f"{record.record_id}: mo1_mode='exact_wrong' declares no "
            "mo1_wrong_values, so the wrong value would be invented"
        )
    candidates = [
        float(value)
        for value in declared
        if isinstance(value, (int, float)) and float(value) != current
    ]
    if not candidates:
        raise ClauseDataError(
            f"{record.record_id}: mo1_wrong_values holds no value distinct "
            f"from the current {current}"
        )
    return candidates[rng.randrange(len(candidates))], "exact_wrong"


def _stale_value(
    record: ClauseRecord,
    current: float,
    rng: random.Random,
    kind: str | None = None,
    *,
    is_floor: bool = False,
) -> tuple[float, str]:
    """Return ``(stale_value, stale_source)`` for a D1 threshold.

    A recorded, primary-verified former value always wins: it replaces synthesis
    with history. Only where the clause's value genuinely never moved (most of
    the lineage carried over unchanged) does the grid supply a believable
    former value instead. Which of the two happened is stamped on the instance
    so the datasheet can report the real-history vs. plausible-synthesis ratio.
    """

    candidates: list[float] = []
    for key in ("prior_versions", "prior_2022"):
        raw = record.check.get(key, [])
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            for value in _raw_scalars(
                item.get("value", {}) if isinstance(item, dict) else {}
            ):
                # Non-numeric priors (an absent deadline, a day-basis change)
                # are real history but not D1 material -- they are D2/D5 shapes,
                # so they must never reach a stale-threshold substitution.
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if float(value) != current:
                        candidates.append(float(value))
    if candidates:
        return candidates[rng.randrange(len(candidates))], "prior_verified"

    grid = _STALE_GRIDS.get(kind or "")
    if grid:
        # The comparator picks the side; the grid picks the value.
        laxer = [
            value for value in grid if (value < current if is_floor else value > current)
        ]
        if not laxer:
            # Emitting the strict side would encode the regulator having
            # *loosened* the rule -- historically false and the opposite of
            # drift. Reject rather than misrepresent the direction.
            raise MutationRejected(
                f"{record.record_id}: no laxer {kind} on the grid for {current}"
            )
        stale = max(laxer) if is_floor else min(laxer)
        _assert_snap_direction(record, current, stale, is_floor)
        return stale, "grid_fallback"
    if kind == "amount_inr":
        stale = _round_amount(current, downward=is_floor)
    else:
        stale = current - 1.0 if is_floor else current + 1.0
    # Every path is asserted, not just the grid: the direction rule is only
    # worth having if it cannot be bypassed by a kind that lacks a grid.
    _assert_snap_direction(record, current, stale, is_floor)
    return stale, "grid_fallback"


def regulated_literals(records: list[ClauseRecord]) -> frozenset[float]:
    """Every numeric value any clause in the corpus mandates, plus what MO-1
    can drift them to.

    MO-0's benign pass must never touch one of these. Scoped corpus-wide, not
    per-record: a literal that is inert in its own program may be the regulated
    value of a clause hosted elsewhere, and MO-0 editing it there would emit a
    conformant instance carrying a real drift.

    Scoped to the values clauses actually *mandate*, and deliberately not to the
    grids' outputs: MO-1 targets a clause's current value, so a decorative
    ``PIC X(45)`` is no decoy for it even though 45 is a value MO-1 can emit.
    Denying the grid outputs too would leave ``_widen_like_mo1`` nothing to draw
    from -- it snaps onto those same grids -- and silently collapse MO-0 back to
    the cosmetic path, which is the bug this control exists to fix.
    """

    values: set[float] = set()
    for record in records:
        current = record.clause.current_value
        if current is None:
            continue
        for _, value in _flatten_value(current):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.add(float(value))
    return frozenset(values)


# A decorative literal: display/layout only, never a bound live logic reads.
_INERT_PIC_RE = re.compile(r"\bPIC\s+[X9]\((\d+)\)", re.IGNORECASE)
_INERT_OCCURS_RE = re.compile(r"\bOCCURS\s+(\d+)", re.IGNORECASE)


def _inert_numeric_sites(
    base: ProgramSource, denylist: frozenset[float]
) -> list[tuple[int, re.Match[str]]]:
    """Widenable literals on fields no PROCEDURE statement mentions at all.

    Proof obligation, not a heuristic: if a field is referenced anywhere in the
    procedure we cannot cheaply prove widening it is inert, so we do not select
    it. Narrowing is never offered -- ``PIC 9(2) -> 9(4)`` on a field feeding a
    loop bound over an ``OCCURS 10`` table is an overrun, which is why liveness
    alone is not enough and the field must be untouched by logic entirely.
    """

    lines = base.text.splitlines()
    try:
        procedure = _procedure_index(lines)
    except MutationRejected:
        return []
    # An 88-level aliases its parent: CLOSPEN5 guards WS-PEN-ENABLED with
    # "IF PENALTY-ON", so the field's own name never appears in the procedure
    # and a name-only check reads it as inert. It is not -- live logic reads it
    # through the condition name. Map each condition name back to its owner
    # before deciding anything is untouched.
    owner_of_condition: dict[str, str] = {}
    parent: str | None = None
    for line in lines[:procedure]:
        if len(line) > 6 and line[6] in "*/":
            continue
        declaration = re.match(
            r"^\s*(?:01|05|10|15|20|25|49)\s+([A-Z0-9-]+)", line, re.IGNORECASE
        )
        if declaration:
            parent = declaration.group(1).upper()
            continue
        condition = re.match(r"^\s*88\s+([A-Z0-9-]+)", line, re.IGNORECASE)
        if condition and parent:
            owner_of_condition[condition.group(1).upper()] = parent

    referenced: set[str] = set()
    for line in lines[procedure:]:
        if len(line) > 6 and line[6] in "*/":
            continue
        referenced.update(_variables(line))
        for name, owner_name in owner_of_condition.items():
            if re.search(rf"\b{re.escape(name)}\b", line, re.IGNORECASE):
                referenced.add(owner_name)

    sites: list[tuple[int, re.Match[str]]] = []
    owner: str | None = None
    for index, line in enumerate(lines[:procedure]):
        if len(line) > 6 and line[6] in "*/":
            continue
        declaration = re.match(r"^\s*(?:01|05|10|15|20|25|49)\s+([A-Z0-9-]+)", line, re.I)
        if declaration:
            owner = declaration.group(1).upper()
        if owner is None or owner in referenced:
            continue
        for pattern in (_INERT_PIC_RE, _INERT_OCCURS_RE):
            for match in pattern.finditer(line):
                # Deliberately NOT value-filtered. Field inertness is the proof:
                # a regulated literal lives on a live field by definition, so it
                # cannot reach here. Value-filtering as well would skip cruft
                # drawn from the grids -- which is exactly what makes MO-0's
                # input distribution identical to MO-1's -- and starve the
                # control back into the cosmetic path.
                sites.append((index, match))
    return sites


def _widen_like_mo1(
    value: float, rng: random.Random, denylist: frozenset[float]
) -> float | None:
    """Widen a decorative literal using MO-1's own value-selection machinery.

    Not calibration against the probe's feature list -- the same generative
    process. MO-1 snaps a numeric onto one of the stale grids (or the 1-2-5
    ladder), so MO-0 does too, and the resulting distribution of digit-width
    changes and divisibility crossings matches by construction. There is no knob
    here to turn, which is the point: tuning to observed features would just move
    the tell.
    """

    grids = sorted(_STALE_GRIDS)
    grid = _STALE_GRIDS[grids[rng.randrange(len(grids))]]
    larger = [item for item in grid if item > value]
    if larger:
        return min(larger)
    try:
        return _round_amount(value, downward=False)
    except MutationRejected:
        return None


def _apply_mo0_numeric(
    base: ProgramSource,
    rng: random.Random,
    denylist: frozenset[float],
    count: int | None = None,
) -> _EditPlan | None:
    """MO-0's matched numeric control: benign edits with MO-1's footprint.

    ``count`` is the caller's, because the two arms must match on *total* edits,
    not on benign ones. The conformant arm draws 1 or 2 benign edits; the
    drifted arm carries the regulated edit plus 0 or 1, so both totals are
    distributed over {1, 2}. Jittering both arms over the same benign range
    would not overlap them -- it would shift one by exactly the regulated edit,
    which is how "drift always has one more edit" becomes the tell.
    """

    sites = _inert_numeric_sites(base, denylist)
    if not sites:
        return None
    wanted = min(len(sites), 1 + rng.randrange(2) if count is None else count)
    if wanted <= 0:
        return None
    # Retry across eligible targets rather than let a None silently drop an
    # edit: asymmetric loss is "absence becomes a statistic" one layer down, and
    # it is what the touched_line_count residual was measuring.
    pool = list(sites)
    rng.shuffle(pool)
    lines = base.text.splitlines()
    edits: list[SurfaceEdit] = []
    touches: list[_Touch] = []
    accepted: list[tuple[int, "re.Match[str]", float]] = []
    for index, match in pool:
        if len(accepted) == wanted:
            break
        old_value = float(match.group(1))
        new_value = _widen_like_mo1(old_value, rng, denylist)
        if new_value is None or new_value <= old_value:
            continue
        accepted.append((index, match, new_value))
    if len(accepted) < wanted:
        return None
    for index, match, new_value in sorted(
        accepted, key=lambda item: (item[0], -item[1].start(1))
    ):
        line = lines[index]
        old_line = line
        lines[index] = (
            line[: match.start(1)]
            + _format_number_like(match.group(1), new_value)
            + line[match.end(1) :]
        )
        edits.append(
            SurfaceEdit("inert_numeric", index + 1, old_line, lines[index])
        )
        touches.append(_Touch(base.program, None, index + 1, index + 1))
    if not edits:
        return None
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=tuple(touches),
        old=edits[0].old.strip(),
        new=edits[0].new.strip(),
        slice_candidates=base.touched_variables,
        surface_edits=tuple(edits),
    )


def _apply_mo0(
    base: ProgramSource,
    record: ClauseRecord,
    rng: random.Random,
    denylist: frozenset[float] = frozenset(),
) -> _EditPlan:
    plan = _apply_mo0_numeric(base, rng, denylist)
    if plan is not None:
        return plan
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


def _slice_units(
    source: ProgramSource, variables: tuple[str, ...]
) -> list[tuple[int, int, str]]:
    """``(line_start, line_end, text)`` units in the backward slice of any var.

    Units, not lines: a COBOL statement spans several lines and its variables
    are spread across them, so line-local matching misses the coupling it is
    looking for.
    """

    with tempfile.TemporaryDirectory(prefix="t22_couple_") as tmp:
        directory = Path(tmp)
        (directory / source.filename).write_text(source.text, encoding="utf-8")
        for name, text in source.files.items():
            (directory / name).write_text(text, encoding="utf-8")
        program = parse_program(directory / source.filename, include_preamble=True)
        graph = build_call_graph(
            [program], {program.program_id: preprocess(source.text)}
        )
        units: dict[tuple[int, int], str] = {}
        for variable in dict.fromkeys(item.upper() for item in variables if item):
            sliced = slice_on(variable, [program], graph, program=None)
            for statement in sliced.statements:
                if statement.ref.program != program.program_id:
                    continue
                units[(statement.ref.line_start, statement.ref.line_end)] = (
                    statement.text
                )
        return [(start, end, text) for (start, end), text in sorted(units.items())]


def _coupled_sites(
    base: ProgramSource, value: float, primary: tuple[int, re.Match[str]]
) -> list[tuple[int, re.Match[str]]]:
    """Occurrences of the regulated literal that denote the same quantity.

    A stale-threshold bug a maintainer would actually ship moves the value
    everywhere it means the same thing. Editing only the comparison and leaving
    the coupled arithmetic on the old value yields a program that contradicts
    itself -- penalty-free at 8 days but charged from day 9 -- which is not
    drift but incoherence, and reads as generated. Coupling is established from
    def-use (slice membership plus a shared variable), never from literal
    equality: an unrelated array bound that happens to be 7 must not move with
    the SLA window.
    """

    sites = [primary]
    lines = base.text.splitlines()
    primary_index, primary_match = primary
    # The quantity the comparison is about.
    anchors = _variables(lines[primary_index])
    if not anchors:
        return sites
    try:
        procedure = _procedure_index(lines)
        # Slice on the touched variables as well as the compared one. The
        # coupled arithmetic *reads* the regulated quantity to produce a
        # downstream value, so it lives in the downstream variable's backward
        # slice, never in the compared variable's own.
        units = _slice_units(
            base, tuple(dict.fromkeys((*anchors, *base.touched_variables)))
        )
    except Exception:
        # DECISION (T2.4b): def-use is Track A's. Where it cannot resolve a
        # locus we ship the single-site edit on the comparison -- the clause's
        # semantic anchor -- rather than guess at coupling.
        return sites
    pattern = _numeric_pattern(value)
    seen = {(primary_index, primary_match.start())}
    for start, end, text in units:
        upper = text.upper()
        if not any(anchor in upper for anchor in anchors):
            continue
        for index in range(start - 1, min(end, len(lines))):
            if index <= procedure or index == primary_index:
                continue
            line = lines[index]
            if len(line) > 6 and line[6] in "*/":
                continue
            for match in pattern.finditer(line):
                if (index, match.start()) in seen:
                    continue
                seen.add((index, match.start()))
                sites.append((index, match))
    return sites


def _apply_mo1(
    base: ProgramSource, record: ClauseRecord, rng: random.Random
) -> _EditPlan:
    path, raw_current = _target_leaf(base, record)
    if not isinstance(raw_current, (int, float)):
        raise MutationRejected("MO-1 requires a numeric current_value leaf")
    current = float(raw_current)
    mode = record.check.get("mo1_mode") if isinstance(record.check, dict) else None
    if mode == "exact_wrong":
        # Declared non-directional: skip the comparator entirely rather than
        # let a fixed constant masquerade as a threshold with a stale side.
        stale, stale_source = _exact_wrong_value(record, current, rng)
    elif mode is not None:
        raise ClauseDataError(f"{record.record_id}: unknown mo1_mode {mode!r}")
    else:
        stale, stale_source = _stale_value(
            record,
            current,
            rng,
            _leaf_kind(record.clause.current_value, path),
            is_floor=_is_floor(record.clause.current_value, path, record.record_id),
        )
    primary = _numeric_occurrence(base.text, current, base.touched_variables)
    sites = _coupled_sites(base, current, primary)
    primary_index, primary_match = primary
    replacement = _format_number_like(primary_match.group(0), stale)
    lines = base.text.splitlines()
    # Right-to-left within a line keeps every later match offset valid.
    for index, match in sorted(sites, key=lambda item: (item[0], -item[1].start())):
        line = lines[index]
        lines[index] = line[: match.start()] + replacement + line[match.end() :]
    touches = tuple(
        _Touch(base.program, None, index + 1, index + 1)
        for index in sorted({index for index, _ in sites})
    )
    variables = _variables(lines[primary_index]) or base.touched_variables
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=touches,
        old=primary_match.group(0),
        new=replacement,
        slice_candidates=tuple(variables),
        stale_source=stale_source,
    )


def _if_block(
    lines: list[str], preferred_variables: tuple[str, ...]
) -> tuple[int, int]:
    procedure = _procedure_index(lines)
    candidates = [
        index
        for index in range(procedure + 1, len(lines))
        if re.search(r"\bIF\b", _control_text(lines[index]), re.IGNORECASE)
    ]
    preferred = [
        index
        for index in candidates
        if any(
            re.search(
                rf"(?<![A-Z0-9-]){re.escape(variable)}(?![A-Z0-9-])",
                _control_text(lines[index]),
                re.IGNORECASE,
            )
            for variable in preferred_variables
        )
    ]
    if not (preferred or candidates):
        raise MutationRejected("no IF block found")
    start = (preferred or candidates)[0]
    depth = 0
    for index in range(start, len(lines)):
        control = _control_text(lines[index])
        depth += len(re.findall(r"(?<!END-)\bIF\b", control, re.IGNORECASE))
        depth -= len(re.findall(r"\bEND-IF\b", control, re.IGNORECASE))
        if index > start and depth <= 0:
            return start, index
    raise MutationRejected("IF block has no END-IF")


def _matching_else(lines: list[str], start: int, end: int) -> int | None:
    """Return the ELSE paired with ``lines[start]``, ignoring nested branches."""

    depth = 0
    for index in range(start, end):
        for token in re.finditer(
            r"\bEND-IF\b|\bIF\b|\bELSE\b", _control_text(lines[index]), re.I
        ):
            keyword = token.group(0).upper()
            if keyword == "IF":
                depth += 1
            elif keyword == "END-IF":
                depth -= 1
            elif depth == 1:
                return index
    return None


def _fallback_guard(line: str) -> str:
    """Turn a violation guard into the ordinary-path guard retained by MO-2."""

    match = _COMPARATOR_RE.search(_control_text(line))
    if match is None or match.group(0) not in {">", ">=", "<", "<="}:
        raise MutationRejected("MO-2 fallback branch has no invertible range guard")
    complement = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}[match.group(0)]
    return line[: match.start()] + complement + line[match.end() :]


def _apply_mo2(base: ProgramSource) -> _EditPlan:
    lines = base.text.splitlines()
    start, end = _if_block(lines, base.touched_variables)
    old = " ".join(line.strip() for line in lines[start : end + 1])
    else_index = _matching_else(lines, start, end)
    if else_index is None:
        # Some conformant bases establish an ordinary default before the
        # required check and continue with unrelated classification logic.
        # Delete only the required branch and label its insertion point; the
        # remaining paragraph still looks maintained and still uses its input.
        del lines[start : end + 1]
        if start >= len(lines):
            raise MutationRejected("MO-2 deletion has no insertion point")
        insertion_line = lines[start].strip()
        variables = tuple(
            dict.fromkeys(
                (
                    *(_variables(old) or base.touched_variables),
                    *_variables(insertion_line),
                )
            )
        )
        return _EditPlan(
            source=replace(base, text=_join_like(base.text, lines)),
            touches=(_Touch(base.program, None, start + 1, start + 1),),
            old=old,
            new="(deleted)",
            slice_candidates=variables,
        )

    fallback = [line for line in lines[else_index + 1 : end] if line.strip()]
    if not fallback:
        raise MutationRejected("MO-2 found an empty fallback branch")

    # Retain the ordinary-path guard, not merely its assignment. An
    # unconditional success stub orphans the date/limit calculation feeding the
    # removed rule and looks less like an incomplete migration than dead code.
    # The missing failure branch still makes the required action disappear.
    replacement = [_fallback_guard(lines[start]), *fallback, lines[end]]
    lines[start : end + 1] = replacement
    variables = _variables(old) or base.touched_variables
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(_Touch(base.program, None, start + 1, start + len(replacement)),),
        old=old,
        new=" ".join(line.strip() for line in replacement),
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
    if base.touched_variables and candidates:
        touched = {variable.upper() for variable in base.touched_variables}
        scores = {
            index: len(touched.intersection(_variables(_control_text(lines[index]))))
            for index, _match in candidates
        }
        best = max(scores.values())
        candidates = [item for item in candidates if scores[item[0]] == best]
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


def _apply_mo3_grace_widening(base: ProgramSource) -> _EditPlan | None:
    """Retain the coherent pre-grace policy that charged from day one."""

    lines = base.text.splitlines()
    index = next(
        (
            index
            for index, line in enumerate(lines)
            if "WS-DAYS-PAST-DUE" in line.upper()
            and re.search(r"\bIF\b.*>\s*3\b", line, re.IGNORECASE)
        ),
        None,
    )
    if index is None:
        return None
    old = lines[index].strip()
    lines[index] = re.sub(r">\s*3\b", "> ZERO", lines[index], count=1)
    new = lines[index].strip()
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(_Touch(base.program, None, index + 1, index + 1),),
        old=old,
        new=new,
        slice_candidates=tuple(dict.fromkeys(base.touched_variables)),
    )


def _apply_mo3_capitalization(base: ProgramSource) -> _EditPlan | None:
    """Fold unpaid charges back into a base the clause excludes them from."""

    lines = base.text.splitlines()
    try:
        procedure = _procedure_index(lines)
    except MutationRejected:
        return None
    touched = {variable.upper() for variable in base.touched_variables}
    for index in range(procedure + 1, len(lines)):
        line = lines[index]
        if len(line) > 6 and line[6] in "*/":
            continue
        match = _UNPAID_TERM_RE.search(line)
        if match is None or match.group(1).upper() not in touched:
            continue
        start = next(
            (
                item
                for item in range(index, procedure, -1)
                if re.search(r"\bCOMPUTE\b", lines[item], re.IGNORECASE)
            ),
            None,
        )
        if start is None or any(
            _HEADER_RE.match(lines[item]) for item in range(start, index + 1)
        ):
            continue
        new_line = line[: match.start()] + line[match.end() :]
        if not new_line.strip():
            continue
        old = line.strip()
        lines[index] = new_line
        return _EditPlan(
            source=replace(base, text=_join_like(base.text, lines)),
            touches=(_Touch(base.program, None, index + 1, index + 1),),
            old=old,
            new=new_line.strip(),
            slice_candidates=tuple(
                dict.fromkeys((match.group(1).upper(), *base.touched_variables))
            ),
        )
    return None


def _apply_mo3(base: ProgramSource) -> _EditPlan:
    """Contradict the clause through a shape a maintainer would plausibly ship."""

    plan = _apply_mo3_grace_widening(base) or _apply_mo3_capitalization(base)
    if plan is None:
        # DECISION (T2.4b): MO-3 emits only recognized contradiction shapes. The
        # retired fallback inverted whatever comparator it found first, which on
        # a sign guard ("IF WS-BASE > ZERO" -> "<= ZERO") made the regulated
        # branch unreachable. An always-false condition is not a contradiction a
        # maintainer ships, and the judge rejected it as artificial. Rejecting
        # costs D3 yield; emitting an implausible mutant costs the benchmark.
        raise MutationRejected("MO-3 found no plausible contradiction shape")
    return plan


def _alternate_reference_value(old: str, existing: set[str]) -> str:
    if old == "D" and "C" in existing and "W" not in existing:
        # The scale D4 base uses D as a conformant placeholder so the emitted
        # mutant can retain the believable, now-stale W (working-day) option.
        return "W"
    plausible_by_width = {
        1: ("A", "D", "B", "P", "S"),
        2: ("CA", "AU", "NZ", "SG", "AE"),
        3: ("STD", "ALT", "OLD", "NEW"),
    }
    for candidate in plausible_by_width.get(len(old), ()):
        if candidate != old and candidate not in existing:
            return candidate
    if old.isdigit():
        return str((int(old) + 1) % (10 ** len(old))).zfill(len(old))
    prefix = old[:-1]
    for suffix in "ABCDEFGHJKLMNPQRSTUVWXY":
        candidate = prefix + suffix
        if candidate != old and candidate not in existing:
            return candidate
    raise MutationRejected("MO-4 could not form a plausible alternate list value")


def _apply_mo4(base: ProgramSource, _rng: random.Random) -> _EditPlan:
    copybooks = sorted(
        name for name in base.files if name.lower().endswith((".cpy", ".cob"))
    )
    candidates: list[
        tuple[int, str, int, str, list[re.Match[str]], re.Match[str] | None]
    ] = []
    for name in copybooks:
        lines = base.files[name].splitlines()
        for index, line in enumerate(lines):
            if "88 " not in line.upper() or "VALUE" not in line.upper():
                continue
            literals = list(re.finditer(r"'([^']+)'", line))
            if not literals:
                continue
            condition = re.search(r"\b88\s+([A-Z0-9-]+)", line, re.IGNORECASE)
            condition_name = condition.group(1).upper() if condition else ""
            priority = (2 if "CALENDAR" in condition_name else 0) + (
                1 if len(literals) > 1 else 0
            )
            candidates.append((priority, name, index, line, literals, condition))
    if not candidates:
        raise MutationRejected("MO-4 requires an 88-level VALUES list in a copybook")

    _, name, index, line, literals, condition = max(
        candidates, key=lambda item: (item[0], item[1], -item[2])
    )
    # Preserve the primary/default code and alter a secondary historical entry
    # when the list has one.  This resembles stale reference-table maintenance
    # rather than an impossible sentinel substitution.
    match = literals[-1]
    old = match.group(1)
    existing = {item.group(1) for item in literals}
    new = _alternate_reference_value(old, existing)
    lines = base.files[name].splitlines()
    lines[index] = line[: match.start(1)] + new + line[match.end(1) :]
    files = dict(base.files)
    files[name] = _join_like(base.files[name], lines)
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


def _apply_mo4_member_removal(base: ProgramSource, _rng: random.Random) -> _EditPlan:
    """D4 realized by dropping the last entry of a reference-list 88-level.

    Selected per clause via ``check.d4_mode == "member_removal"``. For reference
    sets whose members are named-identity mnemonics (accepted-OVD codes, UNSC
    mandated-list sources), substituting a generic alternate reads as
    artificial — a stale reference list does not sprout a meaningless code, it
    drops a mandated entry. Country-code style lists keep the substitution path
    in :func:`_apply_mo4`, which is deliberately left unchanged.
    """
    copybooks = sorted(
        name for name in base.files if name.lower().endswith((".cpy", ".cob"))
    )
    candidates: list[
        tuple[int, str, int, str, list[re.Match[str]], re.Match[str] | None]
    ] = []
    for name in copybooks:
        lines = base.files[name].splitlines()
        for index, line in enumerate(lines):
            if "88 " not in line.upper() or "VALUE" not in line.upper():
                continue
            literals = list(re.finditer(r"'([^']+)'", line))
            # Removing from a single-entry list would leave an empty VALUES.
            if len(literals) < 2:
                continue
            condition = re.search(r"\b88\s+([A-Z0-9-]+)", line, re.IGNORECASE)
            candidates.append((len(literals), name, index, line, literals, condition))
    if not candidates:
        raise MutationRejected(
            "MO-4 member removal requires an 88-level VALUES list with >=2 entries"
        )

    _, name, index, line, literals, condition = max(
        candidates, key=lambda item: (item[0], item[1], -item[2])
    )
    removed = literals[-1]
    old = removed.group(1)
    # Drop the trailing entry and its separator, preserving the terminating
    # period and the line itself (line-count fidelity).
    lines = base.files[name].splitlines()
    lines[index] = line[: literals[-2].end()] + line[removed.end() :]
    files = dict(base.files)
    files[name] = _join_like(base.files[name], lines)
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
        new="(deleted)",
        slice_candidates=tuple(variables),
    )


def _apply_mo6_loader_omission(
    base: ProgramSource, lines: list[str], procedure: int
) -> _EditPlan | None:
    """Omit a real rule-table loader, leaving its guarded path disabled.

    The conformant host initializes a default-off domain switch through a named
    setup paragraph. Losing that one PERFORM is a mundane integration error:
    the loader remains maintained and compilable but is no longer called. This
    is preferable to inventing a false flag or claiming a production switch is
    intentionally default-off with no management path.
    """

    item_re = re.compile(
        r"^\s*(?:01|05|10|15|20|25|30|35|40|45|49)\s+"
        r"([A-Z][A-Z0-9-]*)\b.*\bVALUE\s+'N'",
        re.IGNORECASE,
    )
    condition_re = re.compile(
        r"^\s*88\s+([A-Z][A-Z0-9-]*)\b.*\bVALUE\s+'Y'",
        re.IGNORECASE,
    )
    conditions: dict[str, tuple[int, str]] = {}
    latest_disabled_item: tuple[int, str] | None = None
    for index in range(procedure):
        if len(lines[index]) > 6 and lines[index][6] in "*/":
            continue
        item = item_re.search(lines[index])
        if item is not None:
            latest_disabled_item = (index, item.group(1).upper())
            continue
        condition = condition_re.search(lines[index])
        if condition is not None and latest_disabled_item is not None:
            conditions[condition.group(1).upper()] = latest_disabled_item

    targets = {variable.upper() for variable in base.touched_variables}
    for guard_index in range(procedure + 1, len(lines)):
        guard = re.search(
            r"\bIF\s+([A-Z][A-Z0-9-]*)\b",
            _control_text(lines[guard_index]),
            re.IGNORECASE,
        )
        if guard is None:
            continue
        condition_name = guard.group(1).upper()
        declaration = conditions.get(condition_name)
        if declaration is None:
            continue
        try:
            start, end = _if_block(lines, (condition_name,))
        except MutationRejected:
            continue
        block_variables = {
            variable.upper()
            for line in lines[start : end + 1]
            for variable in _variables(line)
        }
        if targets and targets.isdisjoint(block_variables):
            continue

        _declaration_index, flag_name = declaration
        initializer_index = next(
            (
                index
                for index in range(procedure + 1, len(lines))
                if re.search(
                    rf"\bMOVE\s+'Y'\s+TO\s+{re.escape(flag_name)}\b",
                    lines[index],
                    re.IGNORECASE,
                )
            ),
            None,
        )
        if initializer_index is None:
            continue
        paragraph = _paragraph_for(base.text, initializer_index + 1)
        if paragraph is None:
            continue
        perform_index = next(
            (
                index
                for index in range(procedure + 1, guard_index)
                if re.search(
                    rf"\bPERFORM\s+{re.escape(paragraph)}\b",
                    lines[index],
                    re.IGNORECASE,
                )
            ),
            None,
        )
        if perform_index is None:
            continue
        old = lines[perform_index].strip()
        del lines[perform_index]
        return _EditPlan(
            source=replace(base, text=_join_like(base.text, lines)),
            touches=(
                _Touch(
                    base.program,
                    None,
                    perform_index + 1,
                    perform_index + 1,
                ),
            ),
            old=old,
            new="(deleted)",
            slice_candidates=tuple(
                dict.fromkeys((flag_name, condition_name, *base.touched_variables))
            ),
        )
    return None


def _apply_mo6_rollout_flag(
    base: ProgramSource, lines: list[str], procedure: int
) -> _EditPlan | None:
    """Disable an existing domain rollout flag that guards the regulated path.

    A named feature switch is a more credible dead-code mechanism than an
    injected, generator-named compliance flag. The host must prove the link:
    an enabled data item owns an enabled 88-level condition, that condition is
    used as an IF guard, and the guarded block contains a declared target
    variable. Otherwise this shape refuses and MO-6 falls through to its older
    statement/block strategies.
    """

    data_items: dict[str, tuple[int, str]] = {}
    latest_enabled_item: tuple[int, str] | None = None
    item_re = re.compile(
        r"^\s*(?:01|05|10|15|20|25|30|35|40|45|49)\s+"
        r"([A-Z][A-Z0-9-]*)\b.*\bVALUE\s+'Y'",
        re.IGNORECASE,
    )
    condition_re = re.compile(
        r"^\s*88\s+([A-Z][A-Z0-9-]*)\b.*\bVALUE\s+'Y'",
        re.IGNORECASE,
    )
    for index in range(procedure):
        if len(lines[index]) > 6 and lines[index][6] in "*/":
            continue
        item = item_re.search(lines[index])
        if item is not None:
            latest_enabled_item = (index, item.group(1).upper())
            continue
        condition = condition_re.search(lines[index])
        if condition is not None and latest_enabled_item is not None:
            data_items[condition.group(1).upper()] = latest_enabled_item

    targets = {variable.upper() for variable in base.touched_variables}
    for guard_index in range(procedure + 1, len(lines)):
        guard = re.search(
            r"\bIF\s+([A-Z][A-Z0-9-]*)\b",
            _control_text(lines[guard_index]),
            re.IGNORECASE,
        )
        if guard is None:
            continue
        condition_name = guard.group(1).upper()
        declaration = data_items.get(condition_name)
        if declaration is None:
            continue
        try:
            start, end = _if_block(lines, (condition_name,))
        except MutationRejected:
            continue
        block_variables = {
            variable.upper()
            for line in lines[start : end + 1]
            for variable in _variables(line)
        }
        if targets and targets.isdisjoint(block_variables):
            continue

        declaration_index, flag_name = declaration
        old_line = lines[declaration_index]
        lines[declaration_index] = re.sub(
            r"\bVALUE\s+'Y'",
            "VALUE 'N'",
            old_line,
            count=1,
            flags=re.IGNORECASE,
        )
        return _EditPlan(
            source=replace(base, text=_join_like(base.text, lines)),
            touches=(
                _Touch(
                    base.program,
                    None,
                    declaration_index + 1,
                    declaration_index + 1,
                ),
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
            slice_candidates=tuple(
                dict.fromkeys((flag_name, condition_name, *base.touched_variables))
            ),
        )
    return None


def _apply_mo6(base: ProgramSource) -> _EditPlan:
    lines = base.text.splitlines()
    procedure = _procedure_index(lines)
    loader_plan = _apply_mo6_loader_omission(base, lines, procedure)
    if loader_plan is not None:
        return loader_plan
    pilot_flag_index = next(
        (
            index
            for index in range(procedure)
            if "WS-PEN-ENABLED" in lines[index].upper()
            and re.search(r"\bVALUE\s+'Y'", lines[index], re.IGNORECASE)
        ),
        None,
    )
    if pilot_flag_index is not None:
        guard_index = next(
            (
                index
                for index in range(procedure + 1, len(lines))
                if re.search(r"\bIF\s+PENALTY-ON\b", lines[index], re.IGNORECASE)
            ),
            None,
        )
        if guard_index is None:
            raise MutationRejected("MO-6 pilot flag has no guarded penalty path")
        old_line = lines[pilot_flag_index]
        lines[pilot_flag_index] = re.sub(
            r"\bVALUE\s+'Y'",
            "VALUE 'N'",
            old_line,
            count=1,
            flags=re.IGNORECASE,
        )
        return _EditPlan(
            source=replace(base, text=_join_like(base.text, lines)),
            touches=(
                _Touch(
                    base.program,
                    None,
                    pilot_flag_index + 1,
                    pilot_flag_index + 1,
                ),
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
                "WS-PEN-ENABLED",
                "WS-ELAPSED-DAYS",
                "WS-PENALTY-AMT",
            ),
        )

    rollout_plan = _apply_mo6_rollout_flag(base, lines, procedure)
    if rollout_plan is not None:
        return rollout_plan

    primary_variables = base.touched_variables[:1]
    start, end = _if_block(lines, primary_variables)
    block = " ".join(lines[start : end + 1]).upper()
    if primary_variables and not any(
        variable.upper() in block for variable in primary_variables
    ):
        return _apply_mo6_statement(base)
    original = " ".join(line.strip() for line in lines[start : end + 1])
    block_ends_sentence = bool(re.search(r"\.\s*$", lines[end]))
    declaration_index = _working_storage_end(lines, procedure)
    declaration = "       01  WS-COMPLIANCE-FLAG PIC X VALUE 'N'."
    lines.insert(declaration_index, declaration)
    start += 1
    end += 1
    if block_ends_sentence:
        lines[end] = re.sub(r"\.\s*$", "", lines[end])
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    lines.insert(start, f"{indent}IF WS-COMPLIANCE-FLAG = 'Y'")
    sentence_end = "." if block_ends_sentence else ""
    lines.insert(end + 2, f"{indent}END-IF{sentence_end}")
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=(_Touch(base.program, None, start + 1, end + 3),),
        old=original,
        new="always-false WS-COMPLIANCE-FLAG guard",
        slice_candidates=("WS-COMPLIANCE-FLAG",),
    )


def _apply_mo6_statement(base: ProgramSource) -> _EditPlan:
    """Guard a compliance paragraph whose rule is a calculation, not an IF."""

    lines = base.text.splitlines()
    procedure = _procedure_index(lines)
    target = None
    for variable in base.touched_variables:
        target = next(
            (
                index
                for index in range(procedure + 1, len(lines))
                if variable.upper() in lines[index].upper()
            ),
            None,
        )
        if target is not None:
            break
    if target is None:
        raise MutationRejected("MO-6 found no compliance statement to guard")
    verb = re.compile(
        r"\b(?:COMPUTE|ADD|SUBTRACT|MULTIPLY|DIVIDE|MOVE|PERFORM)\b",
        re.IGNORECASE,
    )
    start = next(
        (index for index in range(target, procedure, -1) if verb.search(lines[index])),
        target,
    )
    sentence_end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].rstrip().endswith(".")
        ),
        None,
    )
    if sentence_end is None or any(
        _HEADER_RE.match(line) for line in lines[start : sentence_end + 1]
    ):
        raise MutationRejected("MO-6 compliance statement has no safe sentence end")

    # CBACT04 already carries a first-pass switch that is set to N before the
    # interest paragraph is reached. Reusing it resembles a misplaced legacy
    # rollout guard and avoids an obviously generator-authored compliance flag.
    first_pass_set_index = next(
        (
            index
            for index in range(procedure + 1, target)
            if re.search(
                r"\bMOVE\s+'N'\s+TO\s+WS-FIRST-TIME\b",
                lines[index],
                re.IGNORECASE,
            )
        ),
        None,
    )
    existing_first_pass = first_pass_set_index is not None
    if existing_first_pass:
        guard_variable = "WS-FIRST-TIME"
    else:
        guard_variable = "WS-COMPLIANCE-FLAG"
        declaration_index = _working_storage_end(lines, procedure)
        lines.insert(
            declaration_index, "       01  WS-COMPLIANCE-FLAG PIC X VALUE 'N'."
        )
        start += 1
        sentence_end += 1

    # Keep a trailing transaction write outside the dead calculation. This
    # narrows the drift to the regulated interest accumulation and preserves
    # the surrounding batch workflow.
    trailing_perform = next(
        (
            index
            for index in range(start + 1, sentence_end + 1)
            if re.match(r"^\s*PERFORM\b", lines[index], re.IGNORECASE)
        ),
        None,
    )
    partial_sentence = trailing_perform is not None
    end = (trailing_perform - 1) if trailing_perform is not None else sentence_end
    while end > start and not lines[end].strip():
        end -= 1
    original = " ".join(line.strip() for line in lines[start : end + 1])
    if not partial_sentence:
        lines[end] = re.sub(r"\.\s*$", "", lines[end])
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    for index in range(start, end + 1):
        if lines[index].strip():
            lines[index] = "  " + lines[index]
    lines.insert(start, f"{indent}IF {guard_variable} = 'Y'")
    terminator = "END-IF" if partial_sentence else "END-IF."
    lines.insert(end + 2, f"{indent}{terminator}")
    touches = [_Touch(base.program, None, start + 1, end + 3)]
    if first_pass_set_index is not None:
        touches.append(
            _Touch(
                base.program,
                None,
                first_pass_set_index + 1,
                first_pass_set_index + 1,
                label=False,
            )
        )
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=tuple(touches),
        old=original,
        new=f"always-false {guard_variable} guard",
        slice_candidates=(guard_variable, *base.touched_variables),
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
    """Keep validation intact but let a missing limit bypass its downstream gate."""

    lines = base.text.splitlines()
    gate_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(
                r"\bIF\s+WS-FAIL-REASON\s*=\s*(?:ZERO|0)\b",
                line,
                re.IGNORECASE,
            )
        ),
        None,
    )
    validator_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(
                r"\bIF\s+WS-LIMIT\s*>=\s*WS-PROJ-BAL\b",
                line,
                re.IGNORECASE,
            )
        ),
        None,
    )
    blocker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(
                r"\bMOVE\s+102\s+TO\s+WS-FAIL-REASON\b",
                line,
                re.IGNORECASE,
            )
        ),
        None,
    )
    if None not in (gate_index, validator_index, blocker_index):
        assert gate_index is not None
        assert validator_index is not None
        assert blocker_index is not None
        if not gate_index < validator_index < blocker_index:
            raise MutationRejected("MO-3× validate/gate loci are not ordered safely")

        # A zero/missing configured limit being interpreted as "unlimited" is a
        # narrow, coherent legacy exception. The validator still records error
        # 102 for over-limit transactions and the gate still blocks all other
        # configured-limit failures; only the downstream policy disagrees.
        old_text = lines[gate_index].strip()
        indent = lines[gate_index][
            : len(lines[gate_index]) - len(lines[gate_index].lstrip())
        ]
        added = f"{indent}  OR WS-LIMIT = ZERO"
        lines.insert(gate_index + 1, added)
        validator_index += 1
        blocker_index += 1
        return _EditPlan(
            source=replace(base, text=_join_like(base.text, lines)),
            touches=(
                _Touch(base.program, None, gate_index + 1, gate_index + 2),
                _Touch(
                    base.program,
                    None,
                    validator_index + 1,
                    validator_index + 1,
                    label=False,
                ),
                _Touch(
                    base.program,
                    None,
                    blocker_index + 1,
                    blocker_index + 1,
                    label=False,
                ),
            ),
            old=old_text,
            new=added.strip(),
            slice_candidates=(
                "WS-FAIL-REASON",
                "WS-LIMIT",
                "WS-PROJ-BAL",
                "WS-POSTED",
            ),
        )

    reset_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(
                r"\bMOVE\s+'N'\s+TO\s+WS-CONSENT-ON-FILE\b",
                line,
                re.IGNORECASE,
            )
        ),
        None,
    )
    loader_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(
                r"\bIF\s+WS-CONSENT-REC-FOUND\s*=\s*'Y'",
                line,
                re.IGNORECASE,
            )
        ),
        None,
    )
    blocker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(
                r"\bIF\s+WS-PROJECTED-BAL\s*>\s*WS-CREDIT-LIMIT",
                line,
                re.IGNORECASE,
            )
        ),
        None,
    )
    valid_gate_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"\bIF\s+WS-VALID\s*=\s*'Y'", line, re.IGNORECASE)
        ),
        None,
    )
    if None in (reset_index, loader_index, blocker_index, valid_gate_index):
        raise MutationRejected("MO-3× requires a per-record consent-state host")

    assert reset_index is not None
    assert loader_index is not None
    assert blocker_index is not None
    assert valid_gate_index is not None
    if not (reset_index < valid_gate_index < loader_index < blocker_index):
        raise MutationRejected("MO-3× consent-state loci are not ordered safely")

    # Preserve the per-record consent reset and its blocking validation. The
    # contradiction lives at the later post gate: a zero/missing limit is treated
    # as unlimited, a common legacy default that is over-permissive only for that
    # configuration rather than making every validation result vacuous.
    old_text = lines[valid_gate_index].strip()
    indent = lines[valid_gate_index][
        : len(lines[valid_gate_index]) - len(lines[valid_gate_index].lstrip())
    ]
    added = f"{indent}  OR WS-CREDIT-LIMIT = ZERO"
    lines.insert(valid_gate_index + 1, added)
    loader_index += 1
    blocker_index += 1
    touches = (
        _Touch(base.program, None, valid_gate_index + 1, valid_gate_index + 2),
        _Touch(
            base.program,
            None,
            loader_index + 1,
            loader_index + 1,
            label=False,
        ),
        _Touch(base.program, None, blocker_index + 1, blocker_index + 1, label=False),
    )
    return _EditPlan(
        source=replace(base, text=_join_like(base.text, lines)),
        touches=touches,
        old=old_text,
        new=added.strip(),
        slice_candidates=(
            "WS-CONSENT-ON-FILE",
            "WS-CONSENT-REC-FOUND",
            "WS-PROJECTED-BAL",
            "WS-CREDIT-LIMIT",
            "WS-VALID",
        ),
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
    # DECISION: the corrective batch-chain host shares a default-N flag through
    # a copybook, sets it to Y upstream, and guards the regulated calculation
    # downstream through an 88-level condition name. Mutate the upstream setter;
    # changing the shared default would not model the cross-program failure.
    condition_names: dict[str, set[str]] = {}
    for copy_name, copy_text in sorted(base.files.items()):
        if not copy_name.lower().endswith((".cpy", ".copy")):
            continue
        parent: str | None = None
        for line in copy_text.splitlines():
            declaration = re.search(
                r"^\s*(?:01|05|10|15|20|25|30|35|40|45|49)\s+([A-Z0-9-]+)",
                line,
                re.IGNORECASE,
            )
            if declaration:
                parent = declaration.group(1).upper()
                continue
            condition = re.search(
                r"^\s*88\s+([A-Z0-9-]+).*\bVALUE\s+'Y'",
                line,
                re.IGNORECASE,
            )
            if parent and condition:
                condition_names.setdefault(parent, set()).add(
                    condition.group(1).upper()
                )

    main_lines = base.text.splitlines()
    for name in related:
        lines = base.files[name].splitlines()
        for index, line in enumerate(lines):
            setter = re.search(
                r"\bMOVE\s+'Y'\s+TO\s+((?:WS|LK)-[A-Z0-9-]+)",
                line,
                re.IGNORECASE,
            )
            if setter is None:
                continue
            flag = setter.group(1).upper()
            guards = {flag, *condition_names.get(flag, set())}
            guard_index = next(
                (
                    i
                    for i, main_line in enumerate(main_lines)
                    if re.search(r"\bIF\b", main_line, re.IGNORECASE)
                    and any(
                        re.search(rf"\b{re.escape(guard)}\b", main_line, re.IGNORECASE)
                        for guard in guards
                    )
                ),
                None,
            )
            if guard_index is None:
                continue
            old_line = lines[index]
            lines[index] = re.sub(
                r"\bMOVE\s+'Y'\s+TO\b",
                "MOVE 'N' TO",
                old_line,
                count=1,
                flags=re.IGNORECASE,
            )
            files = dict(base.files)
            files[name] = _join_like(base.files[name], lines)
            related_program = _program_id(files[name], fallback=Path(name).stem)
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
                old=old_line.strip(),
                new=lines[index].strip(),
                slice_candidates=(
                    flag,
                    *sorted(guards - {flag}),
                    *base.touched_variables,
                ),
            )
    raise MutationRejected("MO-6× requires a related program flag initialized to Y")


def _benign_numeric_pass(
    plan: _EditPlan, rng: random.Random, denylist: frozenset[float] | None
) -> _EditPlan:
    """Run MO-0's numeric control over a drifted arm too.

    Without this, "a decorative literal moved" appears only in D7 and the label
    is recoverable from field identity alone -- the monoculture signal, one
    level up. Both arms carry benign numeric edits; only the drifted arm also
    carries the regulated one.
    """

    if denylist is None:
        return plan
    # 0 or 1, against MO-0's 1 or 2: totals match, arms overlap.
    benign = _apply_mo0_numeric(plan.source, rng, denylist, count=rng.randrange(2))
    if benign is None:
        return plan
    return replace(
        plan,
        source=benign.source,
        surface_edits=plan.surface_edits + benign.surface_edits,
    )


def _apply(
    base: ProgramSource,
    record: ClauseRecord,
    op: str,
    rng: random.Random,
    denylist: frozenset[float] | None = None,
) -> _EditPlan:
    if op == "MO-0":
        # None means the caller cannot prove which literals are regulated, so
        # the numeric control is withheld rather than risk editing one.
        return _apply_mo0(base, record, rng, denylist or frozenset())
    if op == "MO-1":
        return _apply_mo1(base, record, rng)
    if op == "MO-2":
        return _apply_mo2(base)
    if op == "MO-3":
        return _apply_mo3(base)
    if op == "MO-4":
        # DECISION (T2.4b): how D4 is realized is clause-driven, not a new
        # operator. Named-identity mnemonic sets (OVD codes, UNSC list sources)
        # drift by losing a mandated entry; generic-token substitution reads as
        # artificial there. Country-code style sets keep the substitution path.
        if (
            isinstance(record.check, dict)
            and record.check.get("d4_mode") == "member_removal"
        ):
            return _apply_mo4_member_removal(base, rng)
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
    denylist: frozenset[float] | None = None,
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
    plan = _apply(base, record, op, rng, denylist)
    if op != "MO-0":
        plan = _benign_numeric_pass(plan, rng, denylist)
    # T2.4b / BL-6 guard: a reference-copybook edit's recorded pre-image must
    # actually exist at the touched locus in the authentic base. This catches a
    # build-time-fabricated reference target (the old CC-29 D4 recorded
    # old='D' against an in-memory-rewritten copybook). Scoped to copybook loci
    # -- the fabrication surface -- to leave interprocedural source touches
    # untouched.
    for touch in plan.touches:
        if not plan.old or touch.file is None:
            continue
        if not touch.file.lower().endswith((".cpy", ".copy")):
            continue
        base_lines = base.files.get(touch.file, "").splitlines()
        idx = touch.line_start - 1
        if not (0 <= idx < len(base_lines) and plan.old in base_lines[idx]):
            raise MutationRejected(
                f"{op} pre-image {plan.old!r} not found at "
                f"{touch.file}:{touch.line_start} in the authentic base"
            )
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

    # An optional per-clause drift story lets a curated record spell out the
    # exact D4 semantics (e.g. whether the mutated literal is itself a
    # clause-named object or a synthetic registry code) so gold_rationale is
    # honest per host rather than a vague class label. Empty for clauses that
    # do not set it, so existing instances are unchanged.
    drift_story = (
        record.check.get("drift_story") if isinstance(record.check, dict) else None
    )
    if drift_type == "D7_conformant":
        line_labels = []
        program_label = paragraph_label = "conformant"
        drift_story = None
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
        if drift_story:
            rationale = f"{rationale} {drift_story}"

    mutation_note = (
        f"{op}; locus={_locus_description(loci)}; old={plan.old!r}; "
        f"new={plan.new!r}; validation={validation.level}"
    )
    # Whether this D1 stale value is real regulatory history or plausible
    # synthesis is a reviewer question; answer it per instance rather than
    # leaving the ratio to be reconstructed.
    if plan.stale_source:
        mutation_note += f"; stale_source={plan.stale_source}"
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
            annotator_notes=drift_story,
        ),
    )
    return MutationResult(
        source=diversified,
        instance=instance,
        validation=validation,
        surface_edits=plan.surface_edits + diversification,
    )
