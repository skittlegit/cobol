"""Exact mutation edits for synthetic benchmark rows.

Each synthetic row's program is its base program (``seed/programs/``) plus a
unified diff in ``data/benchmark/edits/<instance_id>.diff``. The diff is the
exact edit the build made, so what a detector sees is exactly what was
generated, validated, and judged.
"""

from __future__ import annotations

import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EDITS = ROOT / "data" / "benchmark" / "edits"


def edit_path(instance_id: str, root: Path = EDITS) -> Path:
    return root / f"{instance_id}.diff"


def make_diff(before: dict[str, str], after: dict[str, str]) -> str:
    """Unified diff of every file whose text changed (no file adds/removes)."""

    if set(before) != set(after):
        raise ValueError("an edit may not add or remove files")
    parts: list[str] = []
    for name in sorted(before):
        old = before[name].splitlines()
        new = after[name].splitlines()
        if old == new:
            continue
        parts.extend(
            difflib.unified_diff(old, new, f"a/{name}", f"b/{name}", n=1, lineterm="")
        )
    return "\n".join(parts) + ("\n" if parts else "")


def write_edit(
    instance_id: str, before: dict[str, str], after: dict[str, str], root: Path = EDITS
) -> Path | None:
    diff = make_diff(before, after)
    path = edit_path(instance_id, root)
    if not diff:
        path.unlink(missing_ok=True)
        return None
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(diff, encoding="utf-8", newline="\n")
    return path


def apply_edit(instance_id: str, files: dict[str, str], root: Path = EDITS) -> dict[str, str]:
    """Return ``files`` with the row's stored edit applied (unchanged if none)."""

    from cobol_archaeologist.migration.patch import apply

    path = edit_path(instance_id, root)
    if not path.exists():
        return dict(files)
    patched, _ = apply(files, path.read_text(encoding="utf-8"))
    return patched
