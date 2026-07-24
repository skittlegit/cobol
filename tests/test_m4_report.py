"""T4.5 fail-closed report and baseline-context gates."""

from __future__ import annotations

from cobol_archaeologist.eval.report import build_m4_report, write_report
from tests.test_eval_metrics import SEED, _record, _rows


def test_report_refuses_missing_artifacts_and_human_labels(tmp_path):
    report = build_m4_report(
        agent=None,
        dense_rag=None,
        oracle_slice=None,
        verifier_labels_complete=False,
    )

    assert report.status == "NOT_EVALUABLE"
    assert len(report.issues) == 4
    assert report.metrics == {}
    assert report.decisions == {}

    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    write_report(report, json_path, markdown_path)
    assert '"status": "NOT_EVALUABLE"' in json_path.read_text(encoding="utf-8")
    assert "GO" not in markdown_path.read_text(encoding="utf-8").replace(
        "NOT_EVALUABLE", ""
    )


def test_report_names_each_missing_required_system():
    report = build_m4_report(
        agent=[],
        dense_rag=[],
        oracle_slice=[],
        verifier_labels_complete=True,
    )
    assert report.status == "NOT_EVALUABLE"
    assert report.issues == [
        "agent evaluation artifact is missing",
        "dense-RAG evaluation artifact is missing",
        "oracle-slice evaluation artifact is missing",
    ]


def test_complete_paired_artifacts_can_issue_go():
    seed = _rows(SEED)
    paired = seed[:10]
    gold_rows = []
    for clone in range(4):
        for index, row in enumerate(paired):
            instance_id = f"drift_{900000 + clone * 100 + index:06d}"
            locus = row.code_locus.model_copy(
                update={
                    "is_interprocedural": True,
                    "slice_vars": [*row.code_locus.slice_vars, f"PAIR-{clone}"],
                }
            )
            gold_rows.append(
                row.model_copy(
                    update={
                        "instance_id": instance_id,
                        "code_locus": locus,
                    }
                )
            )
    agent = [_record(row) for row in gold_rows]
    oracle = [_record(row) for row in gold_rows]
    drift_template = next(row for row in seed if row.drift_type != "D7_conformant")
    conformant_template = next(row for row in seed if row.drift_type == "D7_conformant")
    dense = []
    for row in gold_rows:
        wrong_template = (
            drift_template
            if row.drift_type == "D7_conformant"
            else conformant_template
        )
        dense.append(
            _record(
                row,
                prediction=wrong_template.model_copy(
                    update={"instance_id": row.instance_id}
                ),
            )
        )

    report = build_m4_report(
        agent=agent,
        dense_rag=dense,
        oracle_slice=oracle,
        verifier_labels_complete=True,
        resamples=500,
    )

    assert report.status == "GO"
    assert report.decisions["overall_f1"]["met"]
    assert report.decisions["interprocedural_vs_dense"]["met"]
    assert report.decisions["t6_reporting_bar"]["pairs"] == 20
    assert report.decisions["oracle_slice_deconfounder"]["loop_adds_value"] is False
