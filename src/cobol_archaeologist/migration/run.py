"""Generate, validate, and report migration patches.

    python -m cobol_archaeologist.migration.run generate [CASE_ID ...]
    python -m cobol_archaeologist.migration.run validate [CASE_ID ...]
    python -m cobol_archaeologist.migration.run report

``generate`` asks the detector model (through ``eval/codex.py``) for a minimal
unified diff that fixes the case's verified finding, then validates it.
``validate`` re-checks the stored patch. Both overwrite the case's files.
Validation needs GnuCOBOL, so run these in WSL (``scripts/wsl_run.sh``).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.migration.case import (
    MIGRATION_ROOT,
    MigrationCase,
    case_dir,
    case_ids,
    load_case,
)
from cobol_archaeologist.migration.validate import Validation, validate


class PatchAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch: str = Field(description="A unified diff against the given files.")
    rationale: str
    intended_behavior: str


def build_prompt(case: MigrationCase, sources: dict[str, str]) -> str:
    listing = "\n\n".join(
        f"FILE {name}\n"
        + "\n".join(f"{n:04d}| {line}" for n, line in enumerate(text.splitlines(), 1))
        for name, text in sorted(sources.items())
    )
    scope = "; ".join(
        f"{s.path} lines " + ", ".join(f"{a}-{b}" for a, b in s.line_spans)
        for s in case.edit_scope
    )
    return f"""\
You are fixing one verified regulatory-compliance finding in legacy COBOL.
Return a minimal unified diff (--- a/FILE, +++ b/FILE, @@ hunks with exact
context) that makes the code satisfy the regulation clause. Change only lines
inside the allowed scope: {scope}. Keep fixed-format COBOL columns (code in
columns 8-72). Do not reformat, rename, or touch unrelated logic. Line numbers
below (NNNN|) are for reference only and are not part of the files.

Verified finding (JSON):
{case.finding.model_dump_json(indent=1)}

Required behaviour after the fix:
{case.intended_behavior}

Source files:
{listing}
"""


def generate_patch(case: MigrationCase, sources: dict[str, str]) -> PatchAnswer:
    from cobol_archaeologist.eval import codex

    result = codex.execute_task(
        prompt=build_prompt(case, sources),
        schema=codex.strict_schema(PatchAnswer),
        sources={},
        support_root=None,
    )
    return PatchAnswer.model_validate_json(result.final_message)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def validate_case(case_id: str, root: Path = MIGRATION_ROOT) -> Validation:
    case, sources = load_case(case_id, root)
    directory = case_dir(case_id, root)
    result = validate(
        case, sources, (directory / "patch.diff").read_text(encoding="utf-8")
    )
    _write(directory / "validation.json", result.model_dump_json(indent=2) + "\n")
    return result


def generate_case(case_id: str, root: Path = MIGRATION_ROOT) -> Validation:
    case, sources = load_case(case_id, root)
    directory = case_dir(case_id, root)
    answer = generate_patch(case, sources)
    patch = answer.patch if answer.patch.endswith("\n") else answer.patch + "\n"
    _write(directory / "patch.diff", patch)
    _write(
        directory / "patch.json",
        json.dumps(
            {
                "rationale": answer.rationale,
                "intended_behavior": answer.intended_behavior,
            },
            indent=2,
        )
        + "\n",
    )
    return validate_case(case_id, root)


def build_report(root: Path = MIGRATION_ROOT) -> dict:
    rows = []
    for case_id in case_ids(root):
        case, _ = load_case(case_id, root)
        path = case_dir(case_id, root) / "validation.json"
        result = (
            Validation.model_validate_json(path.read_text(encoding="utf-8"))
            if path.exists()
            else None
        )
        rows.append(
            {
                "case_id": case_id,
                "instance_id": case.instance_id,
                "finding_source": case.finding_source,
                "drift_type": case.finding.drift_type,
                "interprocedural": case.finding.code_locus.is_interprocedural,
                "outcome": result.outcome if result else "not_run",
                "failed_checks": [
                    c.check_id for c in result.checks if c.status == "fail"
                ]
                if result
                else [],
                "checks": len(result.checks) if result else 0,
            }
        )
    return {
        "cases": rows,
        "passed": sum(r["outcome"] == "pass" for r in rows),
        "failed": sum(r["outcome"] == "fail" for r in rows),
        "not_run": sum(r["outcome"] == "not_run" for r in rows),
    }


def render_report(report: dict) -> str:
    lines = [
        "# Migration report",
        "",
        (
            f"Passed {report['passed']}, failed {report['failed']}, "
            f"not run {report['not_run']} of {len(report['cases'])} cases."
        ),
        "",
        "| case | finding | class | interprocedural | outcome | checks | failed checks |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["cases"]:
        lines.append(
            f"| {row['case_id']} | {row['finding_source']} | {row['drift_type']} | "
            f"{'yes' if row['interprocedural'] else 'no'} | {row['outcome']} | "
            f"{row['checks']} | {', '.join(row['failed_checks']) or '-'} |"
        )
    lines += [
        "",
        (
            "Validation applies each patch, checks the edit scope, compiles every "
            "host program with GnuCOBOL 3.2.0, checks source assertions, confirms "
            "the intended fixtures fail before the patch, and runs every fixture "
            "after it. This is finite fixture-level evidence, not proof of "
            "program equivalence."
        ),
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("generate", "validate", "report"))
    parser.add_argument("cases", nargs="*")
    args = parser.parse_args(argv)
    if args.command in {"generate", "validate"}:
        for case_id in args.cases or case_ids():
            result = (generate_case if args.command == "generate" else validate_case)(
                case_id
            )
            failed = [c.check_id for c in result.checks if c.status == "fail"]
            print(
                f"{case_id}: {result.outcome}"
                + (f" ({', '.join(failed)})" if failed else "")
            )
    report = build_report()
    _write(MIGRATION_ROOT / "report.json", json.dumps(report, indent=2) + "\n")
    _write(MIGRATION_ROOT / "report.md", render_report(report))
    print(f"report: {report['passed']} passed, {report['failed']} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
