from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationSubagentRequest,
)
from cobol_archaeologist.eval.config4_prepare import (
    FREEZE_NAME,
    INDEX_NAME,
    REQUEST_DIRECTORY_NAME,
    STAGING_DIRECTORY_NAME,
    Config4DevPreparation,
    prepare_config4_adaptive_dev,
)
from cobol_archaeologist.eval.materialize import MaterializedSource
from cobol_archaeologist.schemas import (
    CodeLocus,
    DriftInstance,
    Labels,
    Provenance,
    RegulationClause,
    SourceLocus,
)


def _row(instance_id: str, *, program: str = "CASE.cbl") -> DriftInstance:
    return DriftInstance(
        instance_id=instance_id,
        regulation_clause=RegulationClause(
            doc="Test regulation",
            clause_id="1",
            version="2026-01-01",
            effective_date="2026-01-01",
            text="The check must be present.",
            current_value=None,
        ),
        code_locus=CodeLocus(
            loci=(
                SourceLocus(
                    program=Path(program).stem,
                    paragraph="1000-MAIN",
                    file=None,
                    line_span=(1, 2),
                ),
            ),
            slice_vars=(),
            is_interprocedural=False,
        ),
        drift_type="D7_conformant",
        target_path=None,
        labels=Labels(
            program_level="conformant",
            paragraph_level="conformant",
            line_level=[],
        ),
        gold_rationale="fixture only",
        provenance=Provenance(
            source="real_curated",
            base_program=program,
            mutation=None,
            annotator_notes=None,
        ),
    )


def _write_split(root: Path, split: str, rows: list[DriftInstance]) -> None:
    path = root / "data/benchmark/v1" / f"{split}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8"
    )


def _fake_materialize(row: DriftInstance, *, programs_root: Path | None = None):
    del programs_root
    content = f"      PROGRAM-ID. {Path(row.provenance.base_program).stem}.\n"
    content += "           STOP RUN.\n"
    return MaterializedSource(
        main_file=Path(row.provenance.base_program).name,
        files={Path(row.provenance.base_program).name: content},
        source_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config4DevPreparation:
    rows = [_row("drift_100001"), _row("drift_100002", program="OTHER.cbl")]
    _write_split(tmp_path, "dev", rows)
    _write_split(tmp_path, "train", [_row("drift_100003", program="TRAIN.cbl")])
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_prepare.materialize", _fake_materialize
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_prepare.runtime_source_sha256",
        lambda _root: "a" * 64,
    )
    return prepare_config4_adaptive_dev(
        root=tmp_path,
        output_dir=tmp_path / "data/eval/m4/trial-01",
        selection="dev",
        row_ids=["drift_100001", "drift_100002"],
        limit=None,
    )


def test_config4_preparation_is_provider_free_and_one_case_per_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def provider_must_not_run(*args, **kwargs):
        raise AssertionError("provider runner must not be called by preparation")

    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_live.run_config3_adaptive",
        provider_must_not_run,
    )
    preparation = _prepare(tmp_path, monkeypatch)

    assert preparation.provider_calls_performed == 0
    assert preparation.headline is False
    assert preparation.hidden_test_rows == 0
    assert preparation.one_case_per_task is True
    assert preparation.task_count == 2
    assert [pin.ordinal for pin in preparation.request_order] == [1, 2]
    assert len({pin.run_key for pin in preparation.request_order}) == 2
    assert all(pin.source_split == "dev" for pin in preparation.request_order)

    for pin in preparation.request_order:
        request_path = tmp_path / pin.request_path
        request = CollaborationSubagentRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        assert request.model_id == "gpt-5.6-luna"
        assert request.reasoning_effort == "max"
        assert request.authorized_hunts == ("adaptive",)
        assert request.visible_cases == 1
        assert request.group.size == 2
        assert request.group.ordinal == pin.ordinal
        assert request.run_key == pin.run_key
        assert request.request_sha256 == pin.request_sha256
        assert (tmp_path / pin.staging_path / "staging-manifest.json").is_file()


def test_config4_selection_never_reads_or_accepts_test_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dev = _row("drift_100010")
    train = _row("drift_100011", program="TRAIN.cbl")
    test_only = _row("drift_999999", program="TEST.cbl")
    _write_split(tmp_path, "dev", [dev])
    _write_split(tmp_path, "train", [train])
    _write_split(tmp_path, "test", [test_only])
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_prepare.materialize", _fake_materialize
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_prepare.runtime_source_sha256",
        lambda _root: "b" * 64,
    )

    preparation = prepare_config4_adaptive_dev(
        root=tmp_path,
        output_dir=tmp_path / "data/eval/m4/trial-test-exclusion",
        selection="train-dev",
        limit=None,
    )

    assert preparation.task_count == 2
    assert {pin.instance_id for pin in preparation.request_order} == {
        "drift_100010",
        "drift_100011",
    }
    assert "drift_999999" not in {
        pin.instance_id for pin in preparation.request_order
    }
    assert all(pin.source_split in {"dev", "train"} for pin in preparation.request_order)


def test_config4_resume_is_byte_identical_and_refuses_changed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _prepare(tmp_path, monkeypatch)
    output = tmp_path / "data/eval/m4/trial-01"
    tracked = {
        path.relative_to(output): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }

    second = _prepare(tmp_path, monkeypatch)
    assert second == first
    assert {
        path.relative_to(output): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    } == tracked
    assert (output / FREEZE_NAME).is_file()
    assert (output / INDEX_NAME).is_file()
    assert (output / REQUEST_DIRECTORY_NAME).is_dir()
    assert (output / STAGING_DIRECTORY_NAME).is_dir()

    # A changed source identity cannot silently resume under the prior freeze.
    def changed_materialize(row: DriftInstance, *, programs_root: Path | None = None):
        del programs_root
        source = _fake_materialize(row)
        changed = source.files[source.main_file] + "CHANGED\n"
        return MaterializedSource(
            main_file=source.main_file,
            files={source.main_file: changed},
            source_sha256=hashlib.sha256(changed.encode("utf-8")).hexdigest(),
        )

    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_prepare.materialize", changed_materialize
    )
    with pytest.raises(RuntimeError, match="immutable configuration-4 artifact"):
        prepare_config4_adaptive_dev(
            root=tmp_path,
            output_dir=output,
            selection="dev",
            row_ids=["drift_100001", "drift_100002"],
            limit=None,
        )
