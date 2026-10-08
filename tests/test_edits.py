"""Exact mutation edits stored as unified diffs."""

from __future__ import annotations

import pytest

from cobol_archaeologist.benchmark.edits import (
    apply_edit,
    edit_path,
    make_diff,
    write_edit,
)

BEFORE = {
    "MAIN.cbl": "       PROCEDURE DIVISION.\n           IF WS-AGE > 30\n           STOP RUN.\n",
    "LIMIT.cpy": "       01  WS-CAP PIC 9(5) VALUE 5000.\n",
}


def test_edit_round_trips_across_files(tmp_path):
    after = {
        "MAIN.cbl": BEFORE["MAIN.cbl"].replace("> 30", ">= 30"),
        "LIMIT.cpy": BEFORE["LIMIT.cpy"].replace("5000", "6000"),
    }

    path = write_edit("drift_000001", BEFORE, after, root=tmp_path)

    assert path == edit_path("drift_000001", tmp_path)
    assert "--- a/LIMIT.cpy" in path.read_text(encoding="utf-8")
    assert apply_edit("drift_000001", BEFORE, root=tmp_path) == after


def test_unchanged_files_write_no_edit(tmp_path):
    assert make_diff(BEFORE, dict(BEFORE)) == ""
    assert write_edit("drift_000002", BEFORE, dict(BEFORE), root=tmp_path) is None
    assert apply_edit("drift_000002", BEFORE, root=tmp_path) == BEFORE


def test_edit_may_not_add_or_remove_files():
    with pytest.raises(ValueError, match="add or remove"):
        make_diff(BEFORE, {"MAIN.cbl": BEFORE["MAIN.cbl"]})
