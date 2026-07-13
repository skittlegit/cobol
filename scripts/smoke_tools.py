#!/usr/bin/env python
"""T1.6 smoke: answer a real drift-investigation question through the tool layer.

    "Which paragraphs write ACCT-CURR-BAL, and who calls them?"

This is the question an agent asks when it wants to know where an account
balance can change — the entry point to every D1/D5 threshold question about
CardDemo. It is answered here using ONLY ToolLayer calls (trace_variable +
find_callers), with no reach-through to the parser, call graph, or dataflow
modules underneath: if this script works, the agent's view of the corpus is
sufficient, and the seam Track C swaps against is real.

Prints JSON to stdout; tests/fixtures/smoke/acct_curr_bal.json is the asserted
answer (tests/test_tools.py::test_smoke_script_matches_fixture).

    python scripts/smoke_tools.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from cobol_archaeologist.tool_types import ToolLayer
from cobol_archaeologist.tools import RealToolLayer

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"

VARIABLE = "ACCT-CURR-BAL"


def who_writes(tools: ToolLayer, variable: str) -> list[dict]:
    """Paragraphs that write `variable`, and each one's callers — ToolLayer only."""
    trace = tools.trace_variable(variable)

    writers: dict[tuple[str, str], list[dict]] = {}
    for site in trace.sites:
        if site.kind != "def":
            continue
        key = (site.ref.program, site.ref.paragraph or "")
        writers.setdefault(key, []).append({
            "line": site.ref.line_start,
            "statement_kind": site.statement_kind,
        })

    answer = []
    for (program, paragraph), writes in sorted(writers.items()):
        callers = tools.find_callers(program, paragraph)
        answer.append({
            "program": program,
            "paragraph": paragraph,
            "writes": sorted(writes, key=lambda w: w["line"]),
            "callers": [
                {"program": c.program, "paragraph": c.paragraph}
                for c in sorted(callers, key=lambda c: (c.program, c.paragraph))
            ],
        })
    return answer


def main() -> int:
    if not CARDDEMO.is_dir():
        print("corpora not fetched (run scripts/fetch_corpora.sh)", file=sys.stderr)
        return 2

    tools = RealToolLayer(
        corpus_root=CARDDEMO / "app" / "cbl",
        copybook_paths=[CARDDEMO / "app" / "cpy", CARDDEMO / "app" / "cpy-bms"],
    )
    print(json.dumps({"variable": VARIABLE, "written_by": who_writes(tools, VARIABLE)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
