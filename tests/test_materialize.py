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


def _mutation_field(row: DriftInstance, field: str) -> str:
    mutation = row.provenance.mutation or ""
    return ast.literal_eval(
        next(
            segment.strip().partition("=")[2]
            for segment in mutation.split(";")[1:]
            if segment.strip().startswith(f"{field}=")
        )
    )


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


def test_materializer_blanks_deletion_without_changing_line_count(tmp_path):
    row = _by_operator("MO-2")
    mutation = row.provenance.mutation or ""
    old = ast.literal_eval(
        next(
            segment.strip().partition("=")[2]
            for segment in mutation.split(";")[1:]
            if segment.strip().startswith("old=")
        )
    )
    locus = row.code_locus.loci[0]
    line_count = max(31, locus.line_span[1])
    lines = ["       01 FILLER PIC X.\n"] * line_count
    lines[locus.line_span[0] - 1] = f"       {old}\n"
    (tmp_path / row.provenance.base_program).write_text(
        "".join(lines),
        encoding="utf-8",
    )

    source = materialize(row, programs_root=tmp_path)

    assert old not in source.files[row.provenance.base_program]
    assert len(source.files[row.provenance.base_program].splitlines()) == line_count


def test_materializer_replaces_actual_multiline_non_deletion_block():
    row = next(
        row
        for row in _dev_rows()
        if row.provenance.base_program == "ACTIVAT1.cbl"
        and (row.provenance.mutation or "").startswith("MO-2;")
    )
    base = materialize_base(row)
    source = materialize(row)
    base_text = base.files[row.provenance.base_program]
    materialized_text = source.files[row.provenance.base_program]
    new = _mutation_field(row, "new")

    assert new in materialized_text
    assert _mutation_field(row, "old") not in materialized_text
    assert materialized_text.count("\n") == base_text.count("\n")
    assert len(materialized_text.splitlines()) == len(base_text.splitlines())


def test_all_dev_rows_materialize():
    rows = _dev_rows()

    assert len(rows) == 298
    for row in rows:
        source = materialize(row)
        assert source.files


def test_materializer_rejects_zero_normalized_block_matches(tmp_path):
    row = next(
        row
        for row in _dev_rows()
        if row.provenance.base_program == "ACTIVAT1.cbl"
        and (row.provenance.mutation or "").startswith("MO-2;")
    )
    source_path = PROGRAMS / "train-bases" / row.provenance.base_program
    text = source_path.read_text(encoding="utf-8")
    old = _mutation_field(row, "old")
    broken = text.replace(
        "IF WS-DAYS-SINCE-ISSUE > 30", "IF WS-DAYS-SINCE-ISSUE > 300"
    )
    assert old not in broken
    (tmp_path / row.provenance.base_program).write_text(broken, encoding="utf-8")

    with pytest.raises(MaterializationError, match="normalized block .* matched 0"):
        materialize(row, programs_root=tmp_path)


def test_materializer_rejects_ambiguous_normalized_block_matches(tmp_path):
    row = next(
        row
        for row in _dev_rows()
        if row.provenance.base_program == "ACTIVAT1.cbl"
        and (row.provenance.mutation or "").startswith("MO-2;")
    )
    source_path = PROGRAMS / "train-bases" / row.provenance.base_program
    text = source_path.read_text(encoding="utf-8")
    old = _mutation_field(row, "old")
    expanded = text + "\n" + old.lower() + "\n"
    (tmp_path / row.provenance.base_program).write_text(expanded, encoding="utf-8")
    broad_locus = row.code_locus.loci[0].model_copy(
        update={"line_span": (row.code_locus.loci[0].line_span[0], 100)}
    )
    ambiguous = row.model_copy(
        update={
            "code_locus": row.code_locus.model_copy(update={"loci": [broad_locus]})
        }
    )

    with pytest.raises(MaterializationError, match="normalized block .* matched 2"):
        materialize(ambiguous, programs_root=tmp_path)


def test_materializer_rejects_source_drift_and_ambiguity(tmp_path):
    row = _by_operator("MO-1")
    (tmp_path / row.provenance.base_program).write_text(
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {Path(row.provenance.base_program).stem}.\n",
        encoding="utf-8",
    )
    with pytest.raises(MaterializationError, match="matched 0"):
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
