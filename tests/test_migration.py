"""Migration: patches, cases, and GnuCOBOL validation."""

from __future__ import annotations

import pytest

from cobol_archaeologist.migration import patch
from cobol_archaeologist.migration.case import (
    Fixture,
    MigrationCase,
    case_ids,
    load_case,
)
from cobol_archaeologist.migration.run import build_prompt, build_report
from cobol_archaeologist.migration.validate import validate

FILES = {"A.cbl": "line one\nline two\nline three\n"}


def test_patch_applies_and_reports_changed_lines():
    diff = "--- a/A.cbl\n+++ b/A.cbl\n@@ -2 +2 @@\n-line two\n+line 2\n"
    patched, changed = patch.apply(FILES, diff)
    assert patched["A.cbl"] == "line one\nline 2\nline three\n"
    assert changed == {"A.cbl": {2}}


@pytest.mark.parametrize(
    "diff, message",
    [
        ("--- a/A.cbl\n+++ b/A.cbl\n@@ -2 +2 @@\n-wrong\n+x\n", "context"),
        ("--- a/B.cbl\n+++ b/B.cbl\n@@ -1 +1 @@\n-x\n+y\n", "unknown file"),
        ("--- a/../A.cbl\n+++ b/../A.cbl\n@@ -1 +1 @@\n-x\n+y\n", "unsafe"),
        ("--- /dev/null\n+++ b/N.cbl\n@@ -0,0 +1 @@\n+x\n", "creating"),
        ("--- a/A.cbl\n+++ b/A.cbl\n@@ -2,2 +2 @@\n-line two\n+x\n", "counts"),
        ("", "changes nothing"),
    ],
)
def test_bad_patches_are_rejected(diff, message):
    with pytest.raises(patch.PatchError, match=message):
        patch.apply(FILES, diff)


def test_fixture_rules():
    with pytest.raises(ValueError):
        Fixture(fixture_id="x", host="H", expected_stdout="", perform=("P",))
    with pytest.raises(ValueError):
        Fixture(
            fixture_id="x",
            host="H",
            expected_stdout="",
            perform=("P",),
            observe=("V",),
            initialize=("DISPLAY 'X'",),
        )


def test_all_cases_load_and_carry_intended_and_regression_checks():
    ids = case_ids()
    assert len(ids) == 4
    for case_id in ids:
        case, sources = load_case(case_id)
        assert isinstance(case, MigrationCase)
        assert "intended" in case.checks and len(case.checks) >= 2
        assert all(any(p == s.path for p in sources) for s in case.edit_scope)


def test_prompt_contains_finding_scope_and_numbered_source():
    case, sources = load_case("migration_345332")
    prompt = build_prompt(case, sources)
    assert case.finding.regulation_clause.text in prompt
    assert "0001| " in prompt
    assert case.edit_scope[0].path in prompt


def test_stored_patch_passes_and_a_noop_edit_fails():
    case, sources = load_case("migration_345332")
    from cobol_archaeologist.migration.case import case_dir

    good = (case_dir(case.case_id) / "patch.diff").read_text(encoding="utf-8")
    result = validate(case, sources, good)
    assert result.outcome == "pass", [c for c in result.checks if c.status == "fail"]
    assert any(c.check_id == "intended_detects_drift" for c in result.checks)

    path, (start, _end) = case.edit_scope[0].path, case.edit_scope[0].line_spans[0]
    line = sources[path].splitlines()[start - 1]
    comment = line[:6] + "*" + line[7:]
    bad = f"--- a/{path}\n+++ b/{path}\n@@ -{start} +{start} @@\n-{line}\n+{comment}\n"
    failed = validate(case, sources, bad)
    assert failed.outcome == "fail"


def test_report_counts_outcomes():
    report = build_report()
    assert report["passed"] + report["failed"] + report["not_run"] == len(
        report["cases"]
    )
    assert all(
        row["finding_source"] in {"oracle", "detector"} for row in report["cases"]
    )
