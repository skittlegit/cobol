"""Gold-hidden source materialization of benchmark rows."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cobol_archaeologist.eval.materialize import (
    MaterializationError,
    materialize,
    materialize_base,
)
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"
DEV_SPLIT = BENCHMARK / "dev.jsonl"
PROGRAMS = BENCHMARK / "seed" / "programs"


def _rows() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for split in ("train", "dev", "test")
        for line in (BENCHMARK / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _by_operator(operator: str) -> DriftInstance:
    return next(
        row
        for row in _rows()
        if (row.provenance.mutation or "").startswith(f"{operator};")
    )


def _dev_rows() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in DEV_SPLIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("operator", ["MO-1", "MO-1×", "MO-6×"])
def test_materializes_local_copybook_and_interprogram_edits(operator):
    row = _by_operator(operator)
    source = materialize(row)
    old_new = {}
    for segment in row.provenance.mutation.split(";")[1:]:
        key, separator, value = segment.strip().partition("=")
        if separator and key in {"old", "new"}:
            old_new[key] = ast.literal_eval(value)

    assert source.main_file == row.provenance.base_program
    assert len(source.source_sha256) == 64
    assert old_new["new"] in "\n".join(source.files.values())
    if operator == "MO-1×":
        assert any(name.lower().endswith(".cpy") for name in source.files)
    if operator == "MO-6×":
        assert (
            len([name for name in source.files if name.lower().endswith(".cbl")]) >= 2
        )


def test_every_synthetic_row_is_its_base_plus_its_stored_edit():
    rows = [row for row in _rows() if row.provenance.source == "synthetic"]

    assert len(rows) > 700
    for row in rows:
        source = materialize(row)
        base = materialize_base(row)
        assert source.main_file == row.provenance.base_program
        assert source.source_sha256 != base.source_sha256, row.instance_id


def test_all_dev_rows_materialize():
    rows = _dev_rows()

    assert len(rows) == 673
    for row in rows:
        source = materialize(row)
        assert source.files


def test_synthetic_row_without_stored_edit_is_refused():
    row = _by_operator("MO-1")
    orphan = row.model_copy(update={"instance_id": "drift_999999"})

    with pytest.raises(MaterializationError, match="no stored edit"):
        materialize(orphan)


def test_edit_that_no_longer_applies_to_its_base_is_refused(tmp_path):
    row = _by_operator("MO-1")
    (tmp_path / row.provenance.base_program).write_text(
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {Path(row.provenance.base_program).stem}.\n",
        encoding="utf-8",
    )

    with pytest.raises(MaterializationError, match=row.instance_id):
        materialize(row, programs_root=tmp_path)


def test_materializer_maps_internal_program_id_to_opaque_main_filename(tmp_path):
    row = _rows()[0]
    opaque_name = "OPAQUE-FIXTURE.cbl"
    (tmp_path / opaque_name).write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. INTERNAL-ID.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN.\n"
        "           STOP RUN.\n",
        encoding="utf-8",
    )
    locus = row.code_locus.loci[0].model_copy(
        update={"program": "INTERNAL-ID", "line_span": (4, 5)}
    )
    opaque = row.model_copy(
        update={
            "provenance": row.provenance.model_copy(
                update={"base_program": opaque_name}
            ),
            "code_locus": row.code_locus.model_copy(
                update={"loci": (locus,), "is_interprocedural": False}
            ),
        }
    )

    source = materialize_base(opaque, programs_root=tmp_path)

    assert source.main_file == opaque_name
    assert set(source.files) == {opaque_name}
