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


def _assign_groups(
    groups: dict[str, list[DriftInstance]],
) -> dict[str, str]:
    global_cells = Counter(_cell(item) for items in groups.values() for item in items)
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

    fixed_test = {
        group
        for group, items in groups.items()
        if any(item.provenance.source == "real_curated" for item in items)
    }
    for group in sorted(fixed_test):
        assignments[group] = "test"
        counts["test"].update(_cell(item) for item in groups[group])
        totals["test"] += len(groups[group])

    remaining = sorted(
        (group for group in groups if group not in fixed_test),
        key=lambda group: (-len(groups[group]), group),
    )
    for group in remaining:
        group_cells = Counter(_cell(item) for item in groups[group])
        candidates: list[tuple[float, int, str]] = []
        for split_index, split in enumerate(SPLITS):
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
    return assignments


def _locus_key(instance: DriftInstance) -> str:
    return json.dumps(
        instance.code_locus.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_assignments(
    rows: list[DriftInstance], assignments: dict[str, str]
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
        "Base-program grouping and real-curated test reservation are hard constraints;",
        "`CI-fragile` marks every split × class × stratum cell with n < 10.",
        "",
        "## Split summary",
        "",
        "| split | total | synthetic | real_curated | local | interprocedural | base groups |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    empty_splits = [split for split in SPLITS if not split_rows[split]]
    if empty_splits:
        lines[5:5] = [
            "",
            "**Constraint warning:** "
            + ", ".join(empty_splits)
            + " is empty because real-curated test reservation consumes every "
            "synthetic base except one; splitting that remaining base would leak "
            "program identity.",
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

    groups: dict[str, list[DriftInstance]] = defaultdict(list)
    for item in rows:
        groups[_base_group(item)].append(item)
    assignments = _assign_groups(groups)
    _validate_assignments(rows, assignments)

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
    # DECISION: the current curated seed reserves every synthetic base except
    # OVRLIM1 for test. One of train/dev must therefore be empty. Preserve the
    # work order's hard no-overlap and curated-test constraints and report the
    # infeasibility instead of leaking a base group across splits.

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
