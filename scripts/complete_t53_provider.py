"""Complete the ratified T5.3 targeted provider executions.

This driver deliberately lives outside ``src/`` so the provider runner's
committed-runtime guard remains effective.  It does not weaken that guard and
does not alter any prompt, budget, verifier, or provider setting.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cobol_archaeologist.eval import codex_live
from cobol_archaeologist.eval.baselines import (
    oracle_slice_context,
    rag_baseline_context,
)
from cobol_archaeologist.eval.live import ROOT, _tool_layer, bounded_code_context
from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.eval.run import CONFIG2_SMOKE_SEED
from cobol_archaeologist.rag.search import RegulationSearch

M4_DIR = ROOT / "data" / "eval" / "m4"
M5_DIR = ROOT / "data" / "eval" / "m5"
TARGET_ID = "drift_000021"


def _context_from_question(question: str) -> dict[str, Any]:
    marker = "Visible context (JSON):\n"
    start = question.index(marker) + len(marker)
    end = question.index("\nReturn one finding or abstain.", start)
    return json.loads(question[start:end])


def _m4_reranker_contexts(
    _system_id: str,
    *,
    source_shas: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    path = M4_DIR / "dense_rag.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        instance_id = record["instance_id"]
        if record["source_sha256"] != source_shas.get(instance_id):
            continue
        context = _context_from_question(record["trajectory"]["question"])
        context["retrieval_mode"] = "hybrid_rerank"
        contexts[instance_id] = context
    missing = sorted(set(source_shas) - set(contexts))
    if missing:
        raise RuntimeError(f"M4 reranker contexts missing for: {', '.join(missing)}")
    return contexts


def _target_rows(instance_ids: set[str]):
    rows = codex_live.load_split()
    selected = [row for row in rows if row.instance_id in instance_ids]
    if {row.instance_id for row in selected} != instance_ids:
        raise RuntimeError("requested target rows are absent from frozen v1")
    return selected


def smoke_reranker() -> None:
    original = codex_live.load_reusable_baseline_contexts
    codex_live.load_reusable_baseline_contexts = _m4_reranker_contexts
    try:
        codex_live.run_codex_system(
            "rag_reranker",
            rows=codex_live.load_split(),
            mode="smoke",
            smoke_seed=CONFIG2_SMOKE_SEED,
            output_dir=M5_DIR,
        )
    finally:
        codex_live.load_reusable_baseline_contexts = original


def _run_targeted(system_id: str, instance_ids: set[str]) -> None:
    selected = _target_rows(instance_ids)
    original_mode_rows = codex_live._mode_rows
    original_prerequisite = codex_live._assert_prerequisite
    original_contexts = codex_live.load_reusable_baseline_contexts
    search = RegulationSearch(mode="hybrid_rerank")

    def mode_rows(rows, mode, *, smoke_seed):
        del mode, smoke_seed
        return list(rows)

    def fresh_contexts(_system_id, *, source_shas):
        by_id = {row.instance_id: row for row in selected}
        contexts: dict[str, dict[str, Any]] = {}
        for instance_id, source_sha in source_shas.items():
            row = by_id[instance_id]
            source = materialize(row)
            if source.source_sha256 != source_sha:
                raise RuntimeError(f"materialization changed for {instance_id}")
            if system_id == "rag_reranker":
                context = rag_baseline_context(
                    system_id,
                    row.regulation_clause.text,
                    program=bounded_code_context(source, row.regulation_clause.text),
                    search=search,
                )
            elif system_id == "oracle_slice":
                with tempfile.TemporaryDirectory(prefix="t53-oracle-context-") as temp:
                    tools = _tool_layer(source, Path(temp), search)
                    context = oracle_slice_context(row, tools=tools)
            else:
                raise RuntimeError(f"no baseline context builder for {system_id}")
            contexts[instance_id] = context.model_dump(mode="json")
        return contexts

    codex_live._mode_rows = mode_rows
    codex_live._assert_prerequisite = lambda *args, **kwargs: None
    if system_id in {"rag_reranker", "oracle_slice"}:
        codex_live.load_reusable_baseline_contexts = fresh_contexts
    try:
        codex_live.run_codex_system(
            system_id,
            rows=selected,
            mode="full",
            smoke_seed=CONFIG2_SMOKE_SEED,
            output_dir=M5_DIR / f"{system_id}-rerun",
            regulation_search=search,
        )
    finally:
        codex_live._mode_rows = original_mode_rows
        codex_live._assert_prerequisite = original_prerequisite
        codex_live.load_reusable_baseline_contexts = original_contexts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("smoke-reranker", "rerun-agent", "rerun-reranker", "rerun-oracle"),
    )
    args = parser.parse_args()
    if args.action == "smoke-reranker":
        smoke_reranker()
    elif args.action == "rerun-agent":
        _run_targeted("agent", {TARGET_ID})
    elif args.action == "rerun-reranker":
        _run_targeted("rag_reranker", {TARGET_ID})
    else:
        real_ids = {
            row.instance_id
            for row in codex_live.load_split()
            if row.provenance.source == "real_curated"
        }
        if len(real_ids) != 43:
            raise RuntimeError(f"expected 43 real-curated rows, found {len(real_ids)}")
        _run_targeted("oracle_slice", real_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
