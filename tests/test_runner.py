"""Runner and report, end to end, with the Codex call replaced offline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from cobol_archaeologist.eval import bridge, codex, detector, report, runner
from cobol_archaeologist.model.verify import LexicalEntailer


@pytest.fixture()
def offline(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_execute_task(
        *, prompt, schema, sources, support_root, descriptor=None, **_
    ):
        ((alias, source),) = sources.items()
        calls.append(alias)
        with tempfile.TemporaryDirectory() as temp:
            task = Path(temp)
            source.write_to(task / "cases" / alias)
            entry = dict((descriptor or {})[alias], source_dir=f"cases/{alias}")
            (task / bridge.DESCRIPTOR_NAME).write_text(
                json.dumps({"aliases": {alias: entry}}), encoding="utf-8"
            )
            log = bridge.run_tool(
                alias,
                "read_program",
                {"program": Path(source.main_file).stem},
                task_root=task,
            )
        final = {
            "results": [
                {
                    "alias": alias,
                    "evidence_ledger": [
                        {
                            "observation_step": 1,
                            "hypothesis": "D7_conformant",
                            "bearing": "context",
                            "rationale": "Read the program.",
                        }
                    ],
                    "response": {
                        "kind": "abstain",
                        "thought": "Offline test.",
                        "prediction": None,
                        "claim": None,
                        "exec_probe": None,
                        "static_claim": None,
                        "abstention_reason": "offline test abstention",
                        "final_answer": "",
                    },
                }
            ]
        }
        return codex.TaskResult(
            final_message=json.dumps(final),
            usage=codex.CodexUsage(input_tokens=100, output_tokens=10),
            tool_logs=[log],
            checks=[],
            rejected_commands=0,
            events_sha256="0" * 64,
        )

    monkeypatch.setattr(codex, "execute_task", fake_execute_task)
    monkeypatch.setattr(codex, "check_login", lambda: "Logged in using ChatGPT")
    monkeypatch.setattr(
        codex, "prepare_support_runtime", lambda: ("/support", "f" * 64)
    )
    monkeypatch.setattr(runner, "default_entailer", LexicalEntailer)
    monkeypatch.setattr(runner, "EVAL_ROOT", tmp_path)
    return calls


def _ids(count: int) -> list[str]:
    return [row.instance_id for row in runner.load_split("dev")[:count]]


def test_detector_run_writes_one_record_per_row(offline, tmp_path):
    ids = _ids(2)
    records = runner.run_split(
        "detector", "dev", ids=ids, workers=1, progress=lambda _: None
    )
    assert [record.instance_id for record in records] == ids
    assert all(
        record.abstained and record.system_id == "detector" for record in records
    )
    lines = (
        (tmp_path / "dev" / "detector.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == 2


def test_rerun_resumes_and_new_version_replaces(offline, monkeypatch, tmp_path):
    ids = _ids(2)
    first = runner.run_split(
        "detector", "dev", ids=ids, workers=1, progress=lambda _: None
    )
    assert len(offline) == 2
    runner.run_split("detector", "dev", ids=ids, workers=1, progress=lambda _: None)
    assert len(offline) == 2  # nothing re-run
    monkeypatch.setattr(detector, "PROMPT_VERSION", "detector-test-next")
    records = runner.run_split(
        "detector", "dev", ids=ids, workers=1, progress=lambda _: None
    )
    assert len(offline) == 4  # every row re-run under the new version
    lines = (
        (tmp_path / "dev" / "detector.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == 2  # replaced in place, not appended
    assert {r.run_key for r in records}.isdisjoint({r.run_key for r in first})


def test_infrastructure_failures_are_recorded_and_retried(
    offline, monkeypatch, tmp_path
):
    ids = _ids(1)

    def broken(**_):
        raise RuntimeError("provider down")

    real = codex.execute_task
    monkeypatch.setattr(codex, "execute_task", broken)
    records = runner.run_split(
        "detector", "dev", ids=ids, workers=1, progress=lambda _: None
    )
    assert records[0].infrastructure_error.startswith("RuntimeError: provider down")
    monkeypatch.setattr(codex, "execute_task", real)
    records = runner.run_split(
        "detector", "dev", ids=ids, workers=1, progress=lambda _: None
    )
    assert records[0].infrastructure_error is None


def test_report_is_not_evaluable_when_rows_are_missing(offline, monkeypatch, tmp_path):
    monkeypatch.setattr(
        report, "results_path", lambda split, system: tmp_path / "none.jsonl"
    )
    result = report.build_report("test")
    assert result["decision"] == "NOT_EVALUABLE"
    assert "NOT_EVALUABLE" in report.render_markdown(result)


def test_gates_are_the_predeclared_values():
    assert report.GATES == {
        "t1_f1": 0.70,
        "balanced_accuracy": 0.65,
        "answer_rate": 0.60,
        "answered_accuracy": 0.80,
        "interprocedural_delta_f1": 0.10,
        "interprocedural_p": 0.05,
        "temporal_paired_accuracy": 0.70,
        "temporal_min_pairs": 20,
    }


def test_dev_report_scores_only_current_version_records(offline, monkeypatch, tmp_path):
    ids = _ids(2)
    runner.run_split("detector", "dev", ids=ids, workers=1, progress=lambda _: None)
    monkeypatch.setattr(
        report,
        "results_path",
        lambda split, system: tmp_path / split / f"{system}.jsonl",
    )
    monkeypatch.setattr(codex, "runtime_identity", lambda: "f" * 64)
    current = report.build_report("dev")
    assert current["decision"] == "DEV_ONLY"
    assert current["scored_rows"] == 2
    monkeypatch.setattr(detector, "PROMPT_VERSION", "detector-test-next")
    stale = report.build_report("dev")
    assert stale["decision"] == "NOT_EVALUABLE"


def test_expired_login_stops_the_run_without_recording_rows(
    offline, monkeypatch, tmp_path
):
    def expired(**_):
        raise codex.CodexAuthError("login expired")

    monkeypatch.setattr(codex, "execute_task", expired)
    with pytest.raises(codex.CodexAuthError):
        runner.run_split(
            "detector", "dev", ids=_ids(3), workers=1, progress=lambda _: None
        )
    assert not (tmp_path / "dev" / "detector.jsonl").exists()
