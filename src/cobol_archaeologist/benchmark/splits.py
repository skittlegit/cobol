"""T2.6 deterministic, group-preserving benchmark splits."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from cobol_archaeologist.schemas import DriftInstance


SPLITS = ("train", "dev", "test")
CLASS_ORDER = (
    "D1_stale_threshold",
    "D2_missing_rule",
    "D3_contradictory",
    "D4_stale_reference_data",
    "D5_boundary_error",
    "D6_dead_code",
    "D7_conformant",
)
STRATA = ("local", "interprocedural")
# DECISION: T2.6 does not prescribe ratios. Use the conventional 70/15/15
# target while treating base-program grouping and real-curated test reservation
# as hard constraints; the distribution report exposes resulting deviations.
TARGET_RATIOS = {"train": 0.70, "dev": 0.15, "test": 0.15}


class SplitConfigurationError(RuntimeError):
    """Raised when inputs cannot satisfy the T2.6 integrity constraints."""


@dataclass(frozen=True)
class SplitReport:
    seed: int
    counts: tuple[tuple[str, int], ...]
    group_counts: tuple[tuple[str, int], ...]
    fragile_cells: int


def _load(path: str | Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _base_group(instance: DriftInstance) -> str:
    # DECISION: provenance.base_program is the stable leakage boundary for
    # native and CardDemo instances. Fall back to the source program encoded in
    # the first structural locus only for legacy rows lacking provenance.
    base = instance.provenance.base_program
    if base:
        return Path(base).stem.upper()
    if not instance.code_locus.loci:  # pragma: no cover - schema prevents this
        raise SplitConfigurationError(
            f"{instance.instance_id} has neither base_program nor source locus"
        )
    return instance.code_locus.loci[0].program.upper()


def _stratum(instance: DriftInstance) -> str:
    return (
        "interprocedural"
        if instance.code_locus.is_interprocedural
        else "local"
    )


def _cell(instance: DriftInstance) -> tuple[str, str]:
    return instance.drift_type, _stratum(instance)


def _operator(instance: DriftInstance) -> str:
    mutation = instance.provenance.mutation or ""
    return mutation.split(";", 1)[0]


def _load_roster(path: str | Path | None) -> dict[str, frozenset[str]]:
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    reservations = payload.get("reservations")
    if not isinstance(reservations, dict):
        raise SplitConfigurationError("base roster lacks a reservations object")
    allowed: dict[str, frozenset[str]] = {}
    for base_path, raw_splits in reservations.items():
        if not isinstance(raw_splits, list) or not raw_splits:
            raise SplitConfigurationError(
                f"base roster reservation {base_path!r} has no allowed splits"
            )
        choices = frozenset(raw_splits)
        unknown = choices - set(SPLITS)
        if unknown:
            raise SplitConfigurationError(
                f"base roster reservation {base_path!r} names unknown splits: "
                f"{sorted(unknown)}"
            )
        group = Path(base_path).stem.upper()
        if group in allowed:
            choices &= allowed[group]
            if not choices:
                raise SplitConfigurationError(
                    f"base roster has conflicting reservations for {group}"
                )
        allowed[group] = choices
    return allowed


def _assignment_score(
    counts: dict[str, Counter],
    totals: Counter,
    target_cells: dict[str, dict[tuple[str, str], float]],
    target_totals: dict[str, float],
) -> float:
    score = 0.0
    for split in SPLITS:
        total_target = max(target_totals[split], 1.0)
        score += 2.0 * ((totals[split] - total_target) / total_target) ** 2
        for cell, target in target_cells[split].items():
            denominator = max(target, 1.0)
            score += ((counts[split][cell] - target) / denominator) ** 2
    return score


def _assignment_score_for_groups(
    groups: dict[str, list[DriftInstance]], assignments: dict[str, str]
) -> float:
    global_cells = Counter(
        _cell(item) for items in groups.values() for item in items
    )
    total = sum(len(items) for items in groups.values())
    target_cells = {
        split: {
            cell: count * TARGET_RATIOS[split]
            for cell, count in global_cells.items()
        }
        for split in SPLITS
    }
    target_totals = {
        split: total * TARGET_RATIOS[split] for split in SPLITS
    }
    counts = {split: Counter() for split in SPLITS}
    totals: Counter = Counter()
    for group, items in groups.items():
        split = assignments[group]
        counts[split].update(_cell(item) for item in items)
        totals[split] += len(items)
    return _assignment_score(counts, totals, target_cells, target_totals)


def _purpose_errors(
    groups: dict[str, list[DriftInstance]], assignments: dict[str, str]
) -> list[str]:
    split_rows = {
        split: [
            item
            for group, items in groups.items()
            if assignments[group] == split
            for item in items
        ]
        for split in SPLITS
    }
    synthetic_total = sum(
        item.provenance.source == "synthetic"
        for items in groups.values()
        for item in items
    )
    synthetic_counts = {
        split: sum(
            item.provenance.source == "synthetic"
            for item in split_rows[split]
        )
        for split in SPLITS
    }
    errors: list[str] = []
    if synthetic_counts["dev"] < 0.12 * synthetic_total:
        errors.append("dev has less than 12% of synthetic instances")
    if synthetic_counts["train"] < 0.40 * synthetic_total:
        errors.append("train has less than 40% of synthetic instances")
    for split in ("train", "dev"):
        classes = {item.drift_type for item in split_rows[split]}
        if len(classes) < 5:
            errors.append(f"{split} contains fewer than five classes")

    test_local = [
        item for item in split_rows["test"] if _stratum(item) == "local"
    ]
    local_counts = Counter(item.drift_type for item in test_local)
    for drift_type in CLASS_ORDER:
        if local_counts[drift_type] < 10:
            errors.append(f"test-local {drift_type} has fewer than 10 instances")

    test_interprocedural = [
        item
        for item in split_rows["test"]
        if _stratum(item) == "interprocedural"
    ]
    if len(test_interprocedural) < 30:
        errors.append("test has fewer than 30 interprocedural instances")
    operator_counts = Counter(_operator(item) for item in test_interprocedural)
    for operator in ("MO-1×", "MO-3×", "MO-6×"):
        if operator_counts[operator] < 8:
            errors.append(f"test {operator} has fewer than eight instances")
    return errors


def _purpose_deficit(
    groups: dict[str, list[DriftInstance]], assignments: dict[str, str]
) -> float:
    """Return the total numeric distance from all purpose-level minima.

    Error-count alone cannot guide a whole-group repair when one cell needs two
    smaller groups: the first move improves the cell but leaves the same error
    label. Summing the actual shortfalls gives that intermediate move credit
    without weakening any hard gate.
    """

    split_rows = {
        split: [
            item
            for group, items in groups.items()
            if assignments[group] == split
            for item in items
        ]
        for split in SPLITS
    }
    synthetic_total = sum(
        item.provenance.source == "synthetic"
        for items in groups.values()
        for item in items
    )
    synthetic_counts = {
        split: sum(
            item.provenance.source == "synthetic" for item in split_rows[split]
        )
        for split in SPLITS
    }
    deficit = max(0.0, 0.12 * synthetic_total - synthetic_counts["dev"])
    deficit += max(0.0, 0.40 * synthetic_total - synthetic_counts["train"])
    for split in ("train", "dev"):
        deficit += max(
            0,
            5 - len({item.drift_type for item in split_rows[split]}),
        )

    test_local = [
        item for item in split_rows["test"] if _stratum(item) == "local"
    ]
    local_counts = Counter(item.drift_type for item in test_local)
    deficit += sum(
        max(0, 10 - local_counts[drift_type]) for drift_type in CLASS_ORDER
    )

    test_interprocedural = [
        item
        for item in split_rows["test"]
        if _stratum(item) == "interprocedural"
    ]
    deficit += max(0, 30 - len(test_interprocedural))
    operator_counts = Counter(_operator(item) for item in test_interprocedural)
    deficit += sum(
        max(0, 8 - operator_counts[operator])
        for operator in ("MO-1×", "MO-3×", "MO-6×")
    )
    return float(deficit)


def _repair_assignments(
    groups: dict[str, list[DriftInstance]],
    assignments: dict[str, str],
    allowed: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    """Move whole groups until every purpose gate passes."""

    errors = _purpose_errors(groups, assignments)
    while errors:
        current_rank = (len(errors), _purpose_deficit(groups, assignments))
        repairs: list[
            tuple[int, float, float, str, int, dict[str, str], list[str]]
        ] = []
        for group in sorted(groups):
            current = assignments[group]
            for split_index, split in enumerate(SPLITS):
                if split == current or split not in allowed[group]:
                    continue
                candidate = dict(assignments)
                candidate[group] = split
                candidate_errors = _purpose_errors(groups, candidate)
                candidate_deficit = _purpose_deficit(groups, candidate)
                if (len(candidate_errors), candidate_deficit) >= current_rank:
                    continue
                repairs.append(
                    (
                        len(candidate_errors),
                        candidate_deficit,
                        _assignment_score_for_groups(groups, candidate),
                        group,
                        split_index,
                        candidate,
                        candidate_errors,
                    )
                )
        if not repairs:
            raise SplitConfigurationError(
                "quantitative roster repair cannot satisfy purpose-level gates: "
                + "; ".join(errors)
            )
        (
            _error_count,
            _deficit,
            _score,
            _group,
            _split_index,
            assignments,
            errors,
        ) = min(repairs, key=lambda item: item[:5])
    return assignments


def _assign_groups(
    groups: dict[str, list[DriftInstance]],
    roster: dict[str, frozenset[str]],
) -> dict[str, str]:
    # DECISION: retain T2.6's group-preserving greedy balance, constrain each
    # choice by the roster, then make the smallest whole-group repair needed
    # for the new purpose gates. No repair may split a base or paired locus.
    allowed: dict[str, tuple[str, ...]] = {}
    for group, items in groups.items():
        choices = set(roster.get(group, frozenset(SPLITS)))
        if any(item.provenance.source == "real_curated" for item in items):
            choices &= {"test"}
        if not choices:
            raise SplitConfigurationError(
                f"base group {group} has no split allowed by roster and real->test"
            )
        allowed[group] = tuple(split for split in SPLITS if split in choices)

    global_cells = Counter(
        _cell(item) for items in groups.values() for item in items
    )
    total = sum(len(items) for items in groups.values())
    target_cells = {
        split: {
            cell: count * TARGET_RATIOS[split]
            for cell, count in global_cells.items()
        }
        for split in SPLITS
    }
    target_totals = {
        split: total * TARGET_RATIOS[split] for split in SPLITS
    }
    counts = {split: Counter() for split in SPLITS}
    totals: Counter = Counter()
    assignments: dict[str, str] = {}

    for group in sorted(groups):
        if len(allowed[group]) != 1:
            continue
        split = allowed[group][0]
        assignments[group] = split
        counts[split].update(_cell(item) for item in groups[group])
        totals[split] += len(groups[group])

    remaining = sorted(
        (group for group in groups if group not in assignments),
        key=lambda group: (-len(groups[group]), group),
    )
    for group in remaining:
        group_cells = Counter(_cell(item) for item in groups[group])
        candidates: list[tuple[float, int, str]] = []
        for split_index, split in enumerate(SPLITS):
            if split not in allowed[group]:
                continue
            counts[split].update(group_cells)
            totals[split] += len(groups[group])
            score = _assignment_score(
                counts, totals, target_cells, target_totals
            )
            counts[split].subtract(group_cells)
            totals[split] -= len(groups[group])
            candidates.append((score, split_index, split))
        _, _, chosen = min(candidates)
        assignments[group] = chosen
        counts[chosen].update(group_cells)
        totals[chosen] += len(groups[group])

    return _repair_assignments(groups, assignments, allowed)


def _locus_key(instance: DriftInstance) -> str:
    return json.dumps(
        instance.code_locus.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_assignments(
    rows: list[DriftInstance],
    assignments: dict[str, str],
    roster: dict[str, frozenset[str]],
) -> None:
    real_not_test = [
        item.instance_id
        for item in rows
        if item.provenance.source == "real_curated"
        and assignments[_base_group(item)] != "test"
    ]
    if real_not_test:
        raise SplitConfigurationError(
            f"real-curated rows assigned outside test: {real_not_test[:3]}"
        )
    roster_violations = [
        group
        for group, split in assignments.items()
        if group in roster and split not in roster[group]
    ]
    if roster_violations:  # pragma: no cover - constrained search prevents it
        raise SplitConfigurationError(
            f"base roster reservations violated: {roster_violations[:3]}"
        )
    locus_splits: dict[str, set[str]] = defaultdict(set)
    for item in rows:
        locus_splits[_locus_key(item)].add(assignments[_base_group(item)])
    split_pairs = [key for key, splits in locus_splits.items() if len(splits) > 1]
    if split_pairs:  # pragma: no cover - base grouping should make impossible
        raise SplitConfigurationError("structural code_locus pair crossed splits")


def _write_jsonl(path: Path, rows: list[DriftInstance]) -> None:
    path.write_text(
        "\n".join(item.model_dump_json() for item in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _distribution(
    split_rows: dict[str, list[DriftInstance]],
    assignments: dict[str, str],
    seed: int,
) -> tuple[str, int]:
    lines = [
        "# Benchmark v1-pre Distribution",
        "",
        f"Deterministic seed: `{seed}`. Target ratios: train 70%, dev 15%, test 15%.",
        "Base-program grouping, roster reservations, and real-curated test "
        "reservation are hard constraints;",
        "`CI-fragile` marks every split × class × stratum cell with n < 10.",
        "",
        "## Split summary",
        "",
        "| split | total | synthetic | real_curated | local | interprocedural | base groups |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for split in SPLITS:
        rows = split_rows[split]
        source_counts = Counter(item.provenance.source for item in rows)
        stratum_counts = Counter(_stratum(item) for item in rows)
        groups = {_base_group(item) for item in rows}
        lines.append(
            f"| {split} | {len(rows)} | {source_counts['synthetic']} | "
            f"{source_counts['real_curated']} | {stratum_counts['local']} | "
            f"{stratum_counts['interprocedural']} | {len(groups)} |"
        )

    synthetic_total = sum(
        item.provenance.source == "synthetic"
        for rows in split_rows.values()
        for item in rows
    )
    synthetic_counts = {
        split: sum(
            item.provenance.source == "synthetic" for item in split_rows[split]
        )
        for split in SPLITS
    }
    test_interprocedural = [
        item
        for item in split_rows["test"]
        if _stratum(item) == "interprocedural"
    ]
    operator_counts = Counter(_operator(item) for item in test_interprocedural)
    interprocedural_classes = Counter(
        item.drift_type for item in test_interprocedural
    )
    train_classes = {item.drift_type for item in split_rows["train"]}
    dev_classes = {item.drift_type for item in split_rows["dev"]}
    lines.extend(
        [
            "",
            "## Purpose-level gates",
            "",
            "| gate | required | observed | status |",
            "|---|---:|---:|---|",
            f"| train synthetic share | >= 40% | "
            f"{synthetic_counts['train'] / synthetic_total:.1%} | pass |",
            f"| dev synthetic share | >= 12% | "
            f"{synthetic_counts['dev'] / synthetic_total:.1%} | pass |",
            f"| test interprocedural | >= 30 | {len(test_interprocedural)} | pass |",
            f"| train classes | >= 5 | {len(train_classes)} | pass |",
            f"| dev classes | >= 5 | {len(dev_classes)} | pass |",
            "",
            "### Test interprocedural operator coverage",
            "",
            "| operator | required | observed | status |",
            "|---|---:|---:|---|",
        ]
    )
    for operator in ("MO-1×", "MO-3×", "MO-6×"):
        lines.append(
            f"| {operator} | >= 8 | {operator_counts[operator]} | pass |"
        )
    lines.extend(
        [
            "",
            "### Test interprocedural class shortfalls",
            "",
            "A zero is an explicit purpose-gate shortfall: no accepted "
            "interprocedural mutation currently emits that class.",
            "",
            "| class | n | coverage |",
            "|---|---:|---|",
        ]
    )
    for drift_type in CLASS_ORDER[:6]:
        count = interprocedural_classes[drift_type]
        coverage = "covered" if count else "named shortfall"
        lines.append(f"| {drift_type} | {count} | {coverage} |")

    lines.extend(
        [
            "",
            "## Split × class × stratum cells",
            "",
            "| split | class | stratum | n | CI status |",
            "|---|---|---|---:|---|",
        ]
    )
    fragile = 0
    for split in SPLITS:
        counts = Counter(_cell(item) for item in split_rows[split])
        for drift_type in CLASS_ORDER:
            for stratum in STRATA:
                count = counts[(drift_type, stratum)]
                status = "CI-fragile" if count < 10 else "ok"
                fragile += count < 10
                lines.append(
                    f"| {split} | {drift_type} | {stratum} | {count} | {status} |"
                )

    lines.extend(
        [
            "",
            "## Base-program assignment",
            "",
            "| base group | split | synthetic | real_curated | total |",
            "|---|---|---:|---:|---:|",
        ]
    )
    all_rows = [item for rows in split_rows.values() for item in rows]
    by_group: dict[str, list[DriftInstance]] = defaultdict(list)
    for item in all_rows:
        by_group[_base_group(item)].append(item)
    for group in sorted(by_group):
        source_counts = Counter(
            item.provenance.source for item in by_group[group]
        )
        lines.append(
            f"| {group} | {assignments[group]} | {source_counts['synthetic']} | "
            f"{source_counts['real_curated']} | {len(by_group[group])} |"
        )
    return "\n".join(lines) + "\n", fragile


def build_splits(
    synthetic_path: str | Path,
    real_curated_path: str | Path,
    output_dir: str | Path,
    *,
    seed: int = 2600,
    roster_path: str | Path | None = None,
) -> SplitReport:
    """Build deterministic v1-pre splits under T2.6 hard constraints."""

    synthetic = _load(synthetic_path)
    real = _load(real_curated_path)
    rows = synthetic + real
    ids = [item.instance_id for item in rows]
    if len(ids) != len(set(ids)):
        raise SplitConfigurationError("split inputs contain duplicate instance IDs")
    if any(item.provenance.source != "synthetic" for item in synthetic):
        raise SplitConfigurationError("synthetic input contains non-synthetic rows")
    if any(item.provenance.source != "real_curated" for item in real):
        raise SplitConfigurationError("real-curated input contains non-curated rows")

    if roster_path is None:
        candidate = Path(synthetic_path).parent / "seed" / "base_roster.json"
        roster_path = candidate if candidate.exists() else None
    roster = _load_roster(roster_path)

    groups: dict[str, list[DriftInstance]] = defaultdict(list)
    for item in rows:
        groups[_base_group(item)].append(item)
    assignments = _assign_groups(groups, roster)
    _validate_assignments(rows, assignments, roster)
    purpose_errors = _purpose_errors(groups, assignments)
    if purpose_errors:  # pragma: no cover - constrained search prevents it
        raise SplitConfigurationError("; ".join(purpose_errors))

    split_rows = {
        split: sorted(
            (
                item
                for item in rows
                if assignments[_base_group(item)] == split
            ),
            key=lambda item: item.instance_id,
        )
        for split in SPLITS
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        _write_jsonl(output_dir / f"{split}.jsonl", split_rows[split])
    distribution, fragile = _distribution(split_rows, assignments, seed)
    (output_dir / "distribution.md").write_text(distribution, encoding="utf-8")
    return SplitReport(
        seed=seed,
        counts=tuple((split, len(split_rows[split])) for split in SPLITS),
        group_counts=tuple(
            (
                split,
                len(
                    {
                        _base_group(item)
                        for item in split_rows[split]
                    }
                ),
            )
            for split in SPLITS
        ),
        fragile_cells=fragile,
    )
