"""Build the held-out test split from the fresh seed bases.

    python -m cobol_archaeologist.benchmark.fresh --out data/benchmark/fresh.jsonl

Every base lives in ``data/benchmark/seed/programs/fresh/`` and is used by no
other split. Each accepted row's exact edit is written to
``data/benchmark/edits/``. Each (base, clause, operator) candidate contributes at most one
row, and rows whose detector-visible (materialized) source would be identical
are dropped, so every test row is a distinct case. Mutations must compile and
change behaviour exactly as for the main build (``mutate``), which needs
GnuCOBOL: run this in WSL.
"""

from __future__ import annotations

import argparse
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cobol_archaeologist.benchmark.edits import edit_path, write_edit
from cobol_archaeologist.benchmark.mutate import (
    ClauseRecord,
    MutationRejected,
    ProgramSource,
    load_clause_records,
    mutate,
    regulated_literals,
)
from cobol_archaeologist.eval.materialize import MaterializationError, materialize

ROOT = Path(__file__).resolve().parents[3]
FRESH = ROOT / "data" / "benchmark" / "seed" / "programs" / "fresh"
CLAUSES = ROOT / "data" / "regulations" / "clauses.jsonl"


@dataclass(frozen=True)
class Host:
    filename: str
    record_id: str
    ops: tuple[str, ...]
    touched: tuple[str, ...]
    target_path: str | None = None
    related: tuple[str, ...] = ()  # other programs of a chain


def _interprocedural_hosts() -> list[Host]:
    """Discover the generated cross-program hosts by their shape."""

    found: list[Host] = []
    programs = sorted(FRESH.glob("*.cbl"))
    for index, path in enumerate(programs):
        text = path.read_text(encoding="utf-8")
        conformant = ("MO-0",) if index % 2 == 0 else ()
        if "-CUTOFF-CAP" in text:
            found.append(
                Host(
                    path.name,
                    "CC-10h",
                    ("MO-1×", *conformant),
                    ("WS-THRESHOLD", "WS-CREDIT-AMT"),
                    "cutoff",
                )
            )
        elif "MOVE 102 TO WS-FAIL-REASON" in text:
            found.append(
                Host(
                    path.name,
                    "CC-06b-v",
                    ("MO-3×", *conformant),
                    ("WS-FAIL-REASON", "WS-LIMIT", "WS-PROJ-BAL", "WS-POSTED"),
                )
            )
        elif "CMP" in path.stem and (FRESH / path.name.replace("CMP", "SET")).exists():
            found.append(
                Host(
                    path.name,
                    "CC-09b-ii",
                    ("MO-6×", *conformant),
                    ("WS-INT-BASE", "WS-INTEREST"),
                    related=(path.name.replace("CMP", "SET"),),
                )
            )
    return found


LOCAL_HOSTS = [
    Host("GRVESC9.cbl", "CC-26c", ("MO-5", "MO-0"), ("WS-AGE-DAYS", "WS-QUEUE")),
    Host(
        "ACTWIN9.cbl",
        "CC-06a-vi",
        ("MO-1", "MO-2", "MO-5", "MO-0"),
        ("WS-ISSUE-AGE", "WS-OTP-AGE", "WS-NEXT-STEP"),
        "activation_window",
    ),
    Host(
        "BOSCR9.cbl",
        "KYC-bo-threshold",
        ("MO-1", "MO-5", "MO-0"),
        ("WS-HOLDING-PCT", "WS-BENEFICIAL"),
    ),
    Host(
        "CKYUP9.cbl",
        "KYC-ckycr-update",
        ("MO-1", "MO-2", "MO-5", "MO-0"),
        ("WS-ELAPSED", "WS-UPL-STATUS"),
    ),
    Host(
        "KYCPR9.cbl",
        "KYC-periodic-updation",
        ("MO-1", "MO-5", "MO-0"),
        ("WS-LAST-YYYY", "WS-NEXT-YYYY", "WS-RISK-BAND"),
        "high_risk",
    ),
    Host(
        "LATFE9.cbl",
        "CC-09b-v",
        ("MO-1", "MO-3", "MO-5", "MO-0"),
        ("WS-DPD", "WS-DUE-OUTSTANDING", "WS-LATE-FEE"),
        "past_due_grace",
    ),
    Host(
        "INTBS9.cbl",
        "CC-09b-ii",
        ("MO-3", "MO-6", "MO-0"),
        ("WS-BASE", "WS-UNPAID-FEES", "WS-INT"),
    ),
    Host(
        "INTRL9.cbl", "CC-09b-ii", ("MO-6", "MO-0"), ("WS-INT-BASE", "WS-INTEREST-AMT")
    ),
    Host(
        "CLSPN9.cbl",
        "CC-08a",
        ("MO-1", "MO-5", "MO-6", "MO-0"),
        ("WS-WORKING-DAYS", "WS-COMPENSATION"),
        "closure_window",
    ),
    Host(
        "CICUP9.cbl",
        "CC-12b",
        ("MO-1", "MO-2", "MO-6", "MO-0"),
        ("WS-SETTLED-AGE", "WS-BUREAU-ACTION"),
    ),
    Host(
        "NOTIC9.cbl",
        "CC-09b-vii",
        ("MO-5", "MO-2", "MO-0"),
        ("WS-NOTICE-GIVEN-DAYS", "WS-CHANGE-ALLOWED"),
    ),
    Host(
        "UNSRV9.cbl", "CC-06a-iv", ("MO-1", "MO-0"), ("WS-REVERSED", "WS-COMPENSATION")
    ),
    Host(
        "INACT9.cbl",
        "CC-08b",
        ("MO-1", "MO-2", "MO-5", "MO-0"),
        ("WS-YEARS-UNUSED", "WS-CLOSURE-STEP"),
        "inactivity_threshold",
    ),
    Host("OVDCK9.cbl", "KYC-ovd-list", ("MO-4", "MO-0"), ("WS-DOC-TYPE",)),
    Host("SANSC9.cbl", "KYC-unsc-screening", ("MO-4", "MO-0"), ("WS-FEED-CODE",)),
    Host(
        "KYCSL8.cbl",
        "KYC-ckycr-update",
        ("MO-2", "MO-1", "MO-5"),
        ("WS-AGE", "WS-SYNC"),
    ),
    Host(
        "ACTCL8.cbl",
        "CC-06a-vi",
        ("MO-2", "MO-1"),
        ("WS-DAYS-ISSUED", "WS-OUTCOME"),
        "activation_window",
    ),
    Host(
        "CICBR8.cbl",
        "CC-12b",
        ("MO-2", "MO-1", "MO-0"),
        ("WS-CLOSED-AGE", "WS-REFRESH"),
    ),
    Host("OVDKY8.cbl", "KYC-ovd-list", ("MO-4",), ("WS-PROOF-CODE",)),
    Host("OVDBR7.cbl", "KYC-ovd-list", ("MO-4", "MO-0"), ("WS-ID-CODE",)),
    Host("SANRT8.cbl", "KYC-unsc-screening", ("MO-4",), ("WS-LIST-ID",)),
]


def hosts() -> list[Host]:
    return _interprocedural_hosts() + LOCAL_HOSTS


def _source(host: Host) -> ProgramSource:
    files = {name: (FRESH / name).read_text(encoding="utf-8") for name in host.related}
    return ProgramSource.from_path(
        FRESH / host.filename,
        files=files,
        touched_variables=host.touched,
        target_path=host.target_path,
    )


def build(
    *, seed: int, attempts: int = 6, exclude_ids: frozenset[str] = frozenset()
) -> tuple[list, Counter]:
    records = {r.record_id: r for r in load_clause_records(CLAUSES)}
    denylist = regulated_literals(list(records.values()))
    rows = []
    seen_sources: set[str] = set()
    seen_ids: set[str] = set(exclude_ids)
    log: Counter = Counter()
    for host_index, host in enumerate(hosts()):
        base = _source(host)
        record: ClauseRecord = records[host.record_id]
        for op_index, op in enumerate(host.ops):
            for attempt in range(attempts):
                rng = random.Random(
                    seed * 1_000_003 + host_index * 1_009 + op_index * 101 + attempt
                )
                try:
                    result = mutate(base, record, op, rng, denylist)
                except MutationRejected as exc:
                    log[f"{host.filename} {op}: {str(exc)[:80]}"] += 1
                    continue
                row = result.instance
                if row.instance_id in seen_ids:
                    log[f"{host.filename} {op}: duplicate id"] += 1
                    continue
                after = {
                    result.source.filename: result.source.text,
                    **result.source.files,
                }
                before = {
                    name: (FRESH / name).read_text(encoding="utf-8") for name in after
                }
                write_edit(row.instance_id, before, after)
                try:
                    visible = materialize(row).source_sha256
                except MaterializationError as exc:
                    edit_path(row.instance_id).unlink(missing_ok=True)
                    log[
                        f"{host.filename} {op}: does not materialize: {str(exc)[:60]}"
                    ] += 1
                    continue
                if visible in seen_sources:
                    edit_path(row.instance_id).unlink(missing_ok=True)
                    log[f"{host.filename} {op}: duplicate visible source"] += 1
                    continue
                seen_ids.add(row.instance_id)
                seen_sources.add(visible)
                rows.append(row)
                log[f"{host.filename} {op}: accepted"] += 1
                break
    return rows, log


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261007)
    args = parser.parse_args(argv)
    existing = set()
    for split in ("train", "dev"):
        path = ROOT / "data" / "benchmark" / f"{split}.jsonl"
        existing |= {
            line.split('"instance_id":"', 1)[1][:12]
            for line in path.read_text(encoding="utf-8").splitlines()
            if '"instance_id":"' in line
        }
    rows, log = build(seed=args.seed, exclude_ids=frozenset(existing))
    args.out.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    for key, count in sorted(log.items()):
        print(f"{count:3d}  {key}")
    classes = Counter(row.drift_type for row in rows)
    inter = sum(row.code_locus.is_interprocedural for row in rows)
    print(
        f"rows={len(rows)} interprocedural={inter} classes={dict(sorted(classes.items()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
