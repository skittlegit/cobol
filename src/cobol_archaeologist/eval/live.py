"""Resumable M4 execution for agent, dense-RAG, and oracle-slice systems.

This module owns orchestration only. It never exposes benchmark labels or
mutation provenance to a model. Source materialization happens before the
system turn, and every emitted finding still passes the T3.4 verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from cobol_archaeologist.agent.policy import (
    confidence_for_tier,
)
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
from cobol_archaeologist.eval.baselines import (
    dense_rag_context,
    oracle_slice_context,
)
from cobol_archaeologist.eval.materialize import (
    MaterializationError,
    MaterializedSource,
    materialize,
)
from cobol_archaeologist.eval.run import (
    EvaluationRunner,
    RunManifest,
    infrastructure_failure,
    investigate_all_hunts,
    record_outcome,
    repository_commit,
    run_key,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.prompt import AgentResponse, DecisionModel
from cobol_archaeologist.model.provider import (
    OPENAI_MODEL_ID,
    OpenAIDecisionModel,
    ProviderUnavailable,
)
from cobol_archaeologist.model.verify import (
    Entailer,
    Finding,
    VerificationResult,
    default_entailer,
    verify,
)
from cobol_archaeologist.rag.index import tokenize
from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.schemas import DriftInstance
from cobol_archaeologist.tools import RealToolLayer

ROOT = Path(__file__).resolve().parents[3]
SPLIT = ROOT / "data" / "benchmark" / "v1-pre" / "test.jsonl"
OUTPUT_DIR = ROOT / "data" / "eval" / "m4"
PROMPT_VERSION = "m4-live-openai-v2"
TOOL_VERSION = "real-tool-layer-t1.6"
INPUT_REVISION = "3acd8b0edb9d0aec26ba931e92f369fe9d612a3d"
SystemID = Literal["agent", "dense_rag", "oracle_slice"]
SYSTEM_IDS: tuple[SystemID, ...] = ("agent", "dense_rag", "oracle_slice")

# Provider token_count is total input + output usage. The schema and replay
# transcript are intentionally included, so the live ceiling is larger than
# the tiny cached-fixture default while remaining finite and auditable.
AGENT_BUDGET = BudgetSpec(
    max_steps=8,
    max_tool_calls=8,
    max_tokens=65_536,
    wall_clock_timeout_s=600,
)
BASELINE_BUDGET = BudgetSpec(
    max_steps=1,
    max_tool_calls=0,
    max_tokens=16_384,
    wall_clock_timeout_s=180,
)

BASELINE_SYSTEM_PROMPT = """\
Perform one evidence-grounded COBOL compliance classification using only the
supplied context. Do not request tools: this is a single-shot baseline. Return
either a complete DriftInstance-shaped finding with concrete verification
hooks, or an explicit abstention. Copy the supplied regulation clause exactly.
Do not infer from formatting, edit artifacts, git history, mtimes, mutation
provenance, or hidden labels. Unsupported findings must be withheld.
"""


def load_split(path: Path = SPLIT) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def baseline_question(system_id: str, context: BaseModel) -> str:
    """Render only the context authorized for the selected baseline."""

    if system_id not in {"dense_rag", "oracle_slice"}:
        raise ValueError(f"not a single-shot baseline: {system_id}")
    label = "dense-RAG" if system_id == "dense_rag" else "oracle-slice"
    return (
        f"System: {label} single-shot compliance detector.\n"
        "Visible context (JSON):\n"
        f"{context.model_dump_json()}\n"
        "Return one finding or abstain. Tool calls are not available."
    )


def _line_windows(
    files: dict[str, str],
    query: str,
    *,
    window_lines: int = 20,
) -> list[tuple[int, str, int, list[str]]]:
    query_tokens = set(tokenize(query))
    windows: list[tuple[int, str, int, list[str]]] = []
    stride = max(1, window_lines // 2)
    for filename, text in sorted(files.items()):
        lines = text.splitlines()
        for start in range(0, max(1, len(lines)), stride):
            chunk = lines[start : start + window_lines]
            if not chunk:
                continue
            chunk_tokens = set(tokenize("\n".join(chunk)))
            score = len(query_tokens & chunk_tokens)
            windows.append((score, filename, start, chunk))
            if start + window_lines >= len(lines):
                break
    return sorted(windows, key=lambda row: (-row[0], row[1], row[2]))


def bounded_code_context(
    source: MaterializedSource,
    query: str,
    *,
    max_lines: int = 200,
    window_lines: int = 20,
) -> str:
    """Select label-free query-relevant code windows under a hard line cap."""

    selected: list[tuple[str, int, list[str]]] = []
    covered: dict[str, set[int]] = {}
    used = 0
    for _score, filename, start, lines in _line_windows(
        source.files,
        query,
        window_lines=window_lines,
    ):
        indexes = set(range(start, start + len(lines)))
        if indexes & covered.setdefault(filename, set()):
            continue
        room = max_lines - used
        if room <= 0:
            break
        chunk = lines[:room]
        selected.append((filename, start, chunk))
        covered[filename].update(range(start, start + len(chunk)))
        used += len(chunk)
    rendered: list[str] = []
    for filename, start, lines in sorted(selected, key=lambda row: (row[0], row[1])):
        rendered.append(f"FILE {filename} LINES {start + 1}-{start + len(lines)}")
        rendered.extend(
            f"{line_number:04d}: {line}"
            for line_number, line in enumerate(lines, start=start + 1)
        )
    return "\n".join(rendered)


def _trajectory(
    response: AgentResponse,
    *,
    question: str,
    model: DecisionModel,
    verification: VerificationResult | None,
    prediction: DriftInstance | None,
    abstained: bool,
    reason: str | None,
    budget_exhausted: bool,
) -> Trajectory:
    return Trajectory(
        question=question,
        steps=[],
        model_responses=[response],
        verification=verification,
        finding=prediction,
        abstained=abstained,
        abstention_reason=reason,
        budget=BASELINE_BUDGET,
        budget_exhausted=budget_exhausted,
        tokens_used=response.token_count,
        final_answer=response.final_answer
        or (f"Abstained: {reason}" if abstained else verification.evidence),
        model_id=model.model_id,
        seed=model.seed,
    )


def single_shot_record(
    gold: DriftInstance,
    *,
    system_id: SystemID,
    source_sha256: str,
    key: str,
    context: BaseModel,
    tools: RealToolLayer,
    model_factory: Callable[[], DecisionModel],
    entailer: Entailer,
) -> EvaluationRecord:
    """Execute one no-tool baseline turn and verify before any emission."""

    question = baseline_question(system_id, context)
    try:
        model = model_factory()
        started = time.monotonic()
        response = model.respond(
            system_prompt=BASELINE_SYSTEM_PROMPT,
            question=question,
            transcript=[],
        )
        elapsed = time.monotonic() - started
    except Exception as exc:  # noqa: BLE001
        return infrastructure_failure(
            gold,
            system_id=system_id,
            source_sha256=source_sha256,
            key=key,
            reason=f"provider failure: {type(exc).__name__}: {exc}",
        )

    if (
        elapsed >= BASELINE_BUDGET.wall_clock_timeout_s
        or response.token_count > BASELINE_BUDGET.max_tokens
    ):
        reason = (
            "wall-clock budget exhausted"
            if elapsed >= BASELINE_BUDGET.wall_clock_timeout_s
            else "token budget exhausted"
        )
        trajectory = _trajectory(
            response,
            question=question,
            model=model,
            verification=None,
            prediction=None,
            abstained=True,
            reason=reason,
            budget_exhausted=True,
        )
        return EvaluationRecord(
            instance_id=gold.instance_id,
            gold=gold,
            trajectory=trajectory,
            abstained=True,
            abstention_reason=reason,
            system_id=system_id,
            source_sha256=source_sha256,
            run_key=key,
        )

    verification = None
    prediction = None
    reason = response.abstention_reason
    if response.kind == "finding":
        finding = Finding.from_prediction(
            response.prediction,
            claim=response.claim,
        ).model_copy(
            update={
                "exec_probe": response.exec_probe,
                "static_claim": response.static_claim,
            }
        )
        try:
            verification = verify(finding, tools, entailer=entailer)
        except Exception as exc:  # noqa: BLE001
            reason = (
                "verification unavailable; refusing emission: "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            if verification.verified:
                prediction = response.prediction
            else:
                reason = verification.rejected_reason or "finding was not verified"
    elif response.kind == "tool":
        reason = "single-shot baseline requested a tool"
    reason = reason or "model abstained"
    abstained = prediction is None
    trajectory = _trajectory(
        response,
        question=question,
        model=model,
        verification=verification,
        prediction=prediction,
        abstained=abstained,
        reason=reason if abstained else None,
        budget_exhausted=False,
    )
    return EvaluationRecord(
        instance_id=gold.instance_id,
        gold=gold,
        prediction=prediction,
        confidence=(
            confidence_for_tier(verification.tier) if prediction is not None else None
        ),
        verification=verification,
        trajectory=trajectory,
        abstained=abstained,
        abstention_reason=reason if abstained else None,
        system_id=system_id,
        source_sha256=source_sha256,
        run_key=key,
    )


def _tool_layer(
    source: MaterializedSource,
    directory: Path,
    regulation_search: RegulationSearch,
) -> RealToolLayer:
    source.write_to(directory)
    tools = RealToolLayer(corpus_root=directory, copybook_paths=[directory])
    # RealToolLayer owns the public search method; injecting the already-built
    # Track C service avoids reloading two pinned retrieval models per row.
    tools._reg_search = regulation_search
    return tools


def _materialize_all(
    rows: Sequence[DriftInstance],
) -> tuple[dict[str, MaterializedSource], dict[str, str]]:
    materialized: dict[str, MaterializedSource] = {}
    failures: dict[str, str] = {}
    for row in rows:
        try:
            materialized[row.instance_id] = materialize(row)
        except MaterializationError as exc:
            failures[row.instance_id] = str(exc)
    return materialized, failures


def run_live_system(
    system_id: SystemID,
    *,
    rows: Sequence[DriftInstance],
    model_id: str,
    output_dir: Path = OUTPUT_DIR,
    regulation_search: RegulationSearch | None = None,
    entailer: Entailer | None = None,
) -> list[EvaluationRecord]:
    """Run one complete paired system artifact, resuming by frozen run key."""

    if system_id not in SYSTEM_IDS:
        raise ValueError(f"unknown M4 system {system_id!r}")
    commit = repository_commit(ROOT)
    materialized, failures = _materialize_all(rows)
    regulation_search = regulation_search or RegulationSearch()
    entailer = entailer or default_entailer()
    model_factory = lambda: OpenAIDecisionModel(model_id=model_id)
    budget = AGENT_BUDGET if system_id == "agent" else BASELINE_BUDGET
    budget_payload = budget.model_dump(mode="json")
    tool_version = f"{TOOL_VERSION}@{commit}"
    manifest = RunManifest(
        system_id=system_id,
        provider="openai",
        model_id=model_id,
        decoding={
            "temperature": 0.0,
            "reasoning_effort": "none",
            "seed": None,
        },
        budgets=budget_payload,
        repository_commit=commit,
        input_revision=INPUT_REVISION,
        tool_version=tool_version,
        prompt_version=PROMPT_VERSION,
        split_path=SPLIT.relative_to(ROOT).as_posix(),
        split_sha256=hashlib.sha256(SPLIT.read_bytes()).hexdigest(),
        total=len(rows),
    )
    runner = EvaluationRunner(
        Path(output_dir) / f"{system_id}.jsonl",
        Path(output_dir) / f"{system_id}.manifest.json",
    )

    def key_for(gold: DriftInstance) -> str:
        source = materialized.get(gold.instance_id)
        return run_key(
            instance_id=gold.instance_id,
            source_sha256=source.source_sha256 if source else "0" * 64,
            system_id=system_id,
            model_id=model_id,
            budgets=budget_payload,
            prompt_version=PROMPT_VERSION,
            tool_version=tool_version,
            commit=commit,
        )

    def execute(
        gold: DriftInstance,
        _system_context,
        key: str,
    ) -> EvaluationRecord:
        source = materialized.get(gold.instance_id)
        if source is None:
            return infrastructure_failure(
                gold,
                system_id=system_id,
                source_sha256="0" * 64,
                key=key,
                reason=f"materialization failed: {failures[gold.instance_id]}",
            )
        with tempfile.TemporaryDirectory(prefix=f"m4-{system_id}-") as temp:
            tools = _tool_layer(source, Path(temp), regulation_search)
            if system_id == "agent":
                try:
                    outcome = investigate_all_hunts(
                        _system_context,
                        tools=tools,
                        model_factory=model_factory,
                        budget=AGENT_BUDGET,
                        entailer=entailer,
                    )
                except Exception as exc:  # noqa: BLE001
                    return infrastructure_failure(
                        gold,
                        system_id=system_id,
                        source_sha256=source.source_sha256,
                        key=key,
                        reason=f"agent execution failed: {type(exc).__name__}: {exc}",
                    )
                reason = outcome.abstention_reason or ""
                if "ProviderUnavailable" in reason or "provider failure" in reason:
                    return infrastructure_failure(
                        gold,
                        system_id=system_id,
                        source_sha256=source.source_sha256,
                        key=key,
                        reason=reason,
                    )
                return record_outcome(
                    gold,
                    outcome,
                    system_id=system_id,
                    source_sha256=source.source_sha256,
                    key=key,
                )

            if system_id == "dense_rag":
                code = bounded_code_context(source, gold.regulation_clause.text)
                context = dense_rag_context(
                    gold.regulation_clause.text,
                    program=code,
                    tools=tools,
                )
            else:
                context = oracle_slice_context(gold, tools=tools)
            return single_shot_record(
                gold,
                system_id=system_id,
                source_sha256=source.source_sha256,
                key=key,
                context=context,
                tools=tools,
                model_factory=model_factory,
                entailer=entailer,
            )

    return runner.run(
        rows,
        manifest=manifest,
        key_factory=key_for,
        executor=execute,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--system",
        choices=(*SYSTEM_IDS, "all"),
        default="all",
    )
    parser.add_argument(
        "--model",
        default=OPENAI_MODEL_ID,
        help="one pinned OpenAI model used for all selected systems",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        OpenAIDecisionModel(model_id=args.model)
    except ProviderUnavailable as exc:
        raise SystemExit(str(exc)) from exc
    rows = load_split()
    search = RegulationSearch()
    entailer = default_entailer()
    systems = SYSTEM_IDS if args.system == "all" else (args.system,)
    for system_id in systems:
        records = run_live_system(
            system_id,
            rows=rows,
            model_id=args.model,
            regulation_search=search,
            entailer=entailer,
        )
        failures = sum(bool(record.infrastructure_error) for record in records)
        print(
            json.dumps(
                {
                    "system": system_id,
                    "records": len(records),
                    "infrastructure_failures": failures,
                }
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
