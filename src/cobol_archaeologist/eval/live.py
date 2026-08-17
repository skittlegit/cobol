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
    EVIDENCE_MINIMUMS,
    confidence_for_tier,
)
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
from cobol_archaeologist.eval.baselines import (
    RAG_RETRIEVAL_MODES,
    oracle_slice_context,
    plain_llm_context,
    rag_baseline_context,
)
from cobol_archaeologist.eval.materialize import (
    MaterializationError,
    MaterializedSource,
    materialize,
)
from cobol_archaeologist.eval.run import (
    CONFIG2_SMOKE_IDS,
    CONFIG2_SMOKE_SEED,
    REQUIRED_SMOKE_ROWS,
    EvaluationRunner,
    RunManifest,
    infrastructure_failure,
    investigate_all_hunts,
    record_outcome,
    repository_commit,
    run_key,
    seeded_stratified_smoke,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.prompt import (
    AgentResponse,
    DecisionModel,
    respond_with_contract_repair,
)
from cobol_archaeologist.model.provider import (
    OllamaDecisionModel,
    OpenAIDecisionModel,
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
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction
from cobol_archaeologist.tools import RealToolLayer

ROOT = Path(__file__).resolve().parents[3]
SPLIT = ROOT / "data" / "benchmark" / "v1" / "test.jsonl"
OUTPUT_DIR = ROOT / "data" / "eval" / "m4-v3"
PROMPT_VERSIONS = {
    "ollama": "m4-live-ollama-v2",
    "openai": "m4-live-openai-v9",
}
TOOL_VERSION = "real-tool-layer-t1.6"
INPUT_REVISION = "3acd8b0edb9d0aec26ba931e92f369fe9d612a3d"
SCHEMA_VERSION = "3"
REASONING_EFFORT = "low"
DEFAULT_MODEL_IDS = {
    "ollama": "qwen3:4b",
    "openai": "gpt-5.6-luna",
}
# Legacy transport argument retained until the finalizer signature is retired.
# M4-X policy ignores it and derives the real floor from EVIDENCE_MINIMUMS.
MIN_AGENT_ABSTENTION_OBSERVATIONS = 1
# T5.3 Amendment 1: `dense_rag` is retired as a runner identity. Phase 5 splits
# it into `rag_dense` (explicit dense retrieval) and `rag_reranker` (hybrid plus
# cross-encoder, the mode the M4 artifact actually ran), and adds `plain_llm`.
SystemID = Literal[
    "agent",
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
]
ProviderID = Literal["ollama", "openai"]
BASELINE_LABELS: dict[str, str] = {
    "plain_llm": "plain single-shot LLM",
    "rag_dense": "dense-RAG single-shot",
    "rag_reranker": "RAG+reranker single-shot",
    "oracle_slice": "oracle-slice",
}
BASELINE_SYSTEM_IDS: tuple[SystemID, ...] = (
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
)
SYSTEM_IDS: tuple[SystemID, ...] = ("agent", *BASELINE_SYSTEM_IDS)
PROVIDER_IDS: tuple[ProviderID, ...] = ("ollama", "openai")

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
either a complete DriftPrediction-shaped finding and claim with concrete
verification hooks, or an explicit abstention. Copy the supplied regulation
clause exactly. A finding prediction must include instance_id,
regulation_clause, code_locus (loci, slice_vars, is_interprocedural),
drift_type, target_path, labels, and rationale. Return exactly one JSON object
and stop; never append an alternative or correction.
Do not infer from formatting, edit artifacts, git history, mtimes, mutation
provenance, or hidden labels. Unsupported findings must be withheld.
"""


class _RecordIdentityModel:
    """Assign the external record ID after a label-free provider response."""

    def __init__(self, inner: DecisionModel, instance_id: str) -> None:
        self.inner = inner
        self.instance_id = instance_id
        self.model_id = inner.model_id
        self.temperature = inner.temperature
        self.seed = inner.seed

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict],
    ) -> AgentResponse:
        response = self.inner.respond(
            system_prompt=system_prompt,
            question=question,
            transcript=transcript,
        )
        if response.prediction is None:
            return response
        prediction = response.prediction.model_copy(
            update={"instance_id": self.instance_id},
            deep=True,
        )
        return response.model_copy(update={"prediction": prediction}, deep=True)


def load_split(path: Path = SPLIT) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def baseline_question(system_id: str, context: BaseModel) -> str:
    """Render only the context authorized for the selected baseline."""

    if system_id not in BASELINE_LABELS:
        raise ValueError(f"not a single-shot baseline: {system_id}")
    label = BASELINE_LABELS[system_id]
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
    responses: list[AgentResponse],
    *,
    response: AgentResponse,
    question: str,
    model: DecisionModel,
    verification: VerificationResult | None,
    prediction: DriftPrediction | None,
    abstained: bool,
    reason: str | None,
    budget_exhausted: bool,
) -> Trajectory:
    return Trajectory(
        question=question,
        steps=[],
        model_responses=responses,
        verification=verification,
        finding=prediction,
        abstained=abstained,
        abstention_reason=reason,
        budget=BASELINE_BUDGET,
        budget_exhausted=budget_exhausted,
        tokens_used=sum(item.token_count for item in responses),
        contract_repairs=max(0, len(responses) - 1),
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
        response, responses = respond_with_contract_repair(
            model,
            system_prompt=BASELINE_SYSTEM_PROMPT,
            question=question,
            transcript=[],
            max_repairs=BASELINE_BUDGET.max_contract_repairs,
            repair_allowed=lambda rejected: (
                rejected.token_count <= BASELINE_BUDGET.max_tokens
                and time.monotonic() - started < BASELINE_BUDGET.wall_clock_timeout_s
            ),
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
        or sum(item.token_count for item in responses) > BASELINE_BUDGET.max_tokens
    ):
        reason = (
            "wall-clock budget exhausted"
            if elapsed >= BASELINE_BUDGET.wall_clock_timeout_s
            else "token budget exhausted"
        )
        trajectory = _trajectory(
            responses,
            response=response,
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
        responses,
        response=response,
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
    regulation_search: RegulationSearch | None,
) -> RealToolLayer:
    source.write_to(directory)
    tools = RealToolLayer(corpus_root=directory, copybook_paths=[directory])
    # RealToolLayer owns the public search method; injecting the already-built
    # Track C service avoids reloading two pinned retrieval models per row.
    if regulation_search is not None:
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


def _smoke_manifest_path(output_dir: Path, system_id: SystemID) -> Path:
    return Path(output_dir) / "smoke" / f"{system_id}.manifest.json"


def _assert_matching_smoke(
    expected: RunManifest,
    *,
    output_dir: Path,
) -> None:
    """Refuse paid full execution without an exactly matching valid smoke."""

    path = _smoke_manifest_path(output_dir, expected.system_id)
    if not path.exists():
        raise RuntimeError(
            f"full run requires a successful matching --smoke "
            f"{REQUIRED_SMOKE_ROWS} manifest at {path}"
        )
    smoke = RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    fields = (
        "system_id",
        "provider",
        "model_id",
        "decoding",
        "budgets",
        "repository_commit",
        "input_revision",
        "tool_version",
        "prompt_version",
        "split_path",
        "split_sha256",
        "schema_version",
        "smoke_seed",
        "smoke_instance_ids",
    )
    mismatches = [
        name for name in fields if getattr(smoke, name) != getattr(expected, name)
    ]
    successful = (
        smoke.run_mode == "smoke"
        and smoke.smoke_rows == REQUIRED_SMOKE_ROWS
        and smoke.total == REQUIRED_SMOKE_ROWS
        and len(smoke.completed_run_keys) == smoke.total
        and not smoke.infrastructure_failures
        and smoke.validity is not None
        and smoke.validity.completed_rows == smoke.total
        and smoke.validity.infrastructure_failures == 0
        and smoke.validity.status == "VALID"
    )
    if mismatches or not successful:
        detail = (
            f"mismatched fields: {', '.join(mismatches)}"
            if mismatches
            else "smoke did not complete with VALID status"
        )
        raise RuntimeError(f"matching smoke prerequisite failed: {detail}")


def _provider_decoding(provider: ProviderID, system_id: SystemID) -> dict:
    if provider == "ollama":
        decoding = {
            "temperature": 0.0,
            "thinking": False,
            "seed": 2601,
        }
    else:
        decoding = {
            "temperature": None,
            "temperature_parameter": "omitted",
            "reasoning_effort": REASONING_EFFORT,
            "seed": None,
        }
    if system_id == "agent":
        decoding["min_successful_observations_by_drift_type"] = dict(EVIDENCE_MINIMUMS)
    return decoding


def _decision_model(provider: ProviderID, model_id: str) -> DecisionModel:
    if provider == "ollama":
        return OllamaDecisionModel(model_id=model_id)
    return OpenAIDecisionModel(
        model_id=model_id,
        reasoning_effort=REASONING_EFFORT,
    )


def run_live_system(
    system_id: SystemID,
    *,
    rows: Sequence[DriftInstance],
    model_id: str,
    smoke_seed: int,
    provider: ProviderID = "ollama",
    output_dir: Path = OUTPUT_DIR,
    regulation_search: RegulationSearch | None = None,
    entailer: Entailer | None = None,
    smoke: int | None = None,
) -> list[EvaluationRecord]:
    """Run one complete paired system artifact, resuming by frozen run key."""

    if system_id not in SYSTEM_IDS:
        raise ValueError(f"unknown M4 system {system_id!r}")
    if provider not in PROVIDER_IDS:
        raise ValueError(f"unknown M4 provider {provider!r}")
    if smoke_seed != CONFIG2_SMOKE_SEED:
        raise ValueError(
            f"the pinned config-2 smoke seed is {CONFIG2_SMOKE_SEED}, not {smoke_seed}"
        )
    requested_rows = list(rows)
    if smoke is not None:
        if smoke != REQUIRED_SMOKE_ROWS:
            raise ValueError(
                f"config-2 smoke must select exactly {REQUIRED_SMOKE_ROWS} rows"
            )
        run_rows = seeded_stratified_smoke(
            requested_rows,
            seed=smoke_seed,
        )
        smoke_instance_ids = [row.instance_id for row in run_rows]
        if tuple(smoke_instance_ids) != CONFIG2_SMOKE_IDS:
            raise ValueError(
                "the frozen split no longer reproduces the pinned config-2 "
                f"smoke IDs: {tuple(smoke_instance_ids)}"
            )
    else:
        run_rows = requested_rows
        smoke_instance_ids = list(CONFIG2_SMOKE_IDS)
    commit = repository_commit(ROOT)
    budget = AGENT_BUDGET if system_id == "agent" else BASELINE_BUDGET
    budget_payload = budget.model_dump(mode="json")
    tool_version = f"{TOOL_VERSION}@{commit}"
    prompt_version = PROMPT_VERSIONS[provider]
    manifest = RunManifest(
        system_id=system_id,
        provider=provider,
        model_id=model_id,
        decoding=_provider_decoding(provider, system_id),
        budgets=budget_payload,
        repository_commit=commit,
        input_revision=INPUT_REVISION,
        tool_version=tool_version,
        prompt_version=prompt_version,
        split_path=SPLIT.relative_to(ROOT).as_posix(),
        split_sha256=hashlib.sha256(SPLIT.read_bytes()).hexdigest(),
        schema_version=SCHEMA_VERSION,
        run_mode="smoke" if smoke is not None else "full",
        smoke_rows=REQUIRED_SMOKE_ROWS if smoke is not None else None,
        smoke_seed=smoke_seed,
        smoke_instance_ids=smoke_instance_ids,
        total=len(run_rows),
    )
    if smoke is None:
        _assert_matching_smoke(manifest, output_dir=output_dir)

    materialized, failures = _materialize_all(run_rows)
    regulation_search = regulation_search or RegulationSearch()
    entailer = entailer or default_entailer()
    artifact_dir = Path(output_dir) / "smoke" if smoke is not None else Path(output_dir)
    runner = EvaluationRunner(
        artifact_dir / f"{system_id}.jsonl",
        artifact_dir / f"{system_id}.manifest.json",
    )

    def key_for(gold: DriftInstance) -> str:
        source = materialized.get(gold.instance_id)
        return run_key(
            instance_id=gold.instance_id,
            source_sha256=source.source_sha256 if source else "0" * 64,
            system_id=system_id,
            model_id=model_id,
            budgets=budget_payload,
            prompt_version=prompt_version,
            tool_version=tool_version,
            commit=commit,
            schema_version=SCHEMA_VERSION,
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
            def model_factory():
                return _RecordIdentityModel(
                    _decision_model(provider, model_id),
                    gold.instance_id,
                )
            if system_id == "agent":
                try:
                    outcome = investigate_all_hunts(
                        _system_context,
                        tools=tools,
                        model_factory=model_factory,
                        budget=AGENT_BUDGET,
                        entailer=entailer,
                        min_successful_observations_before_abstention=(
                            MIN_AGENT_ABSTENTION_OBSERVATIONS
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    return infrastructure_failure(
                        gold,
                        system_id=system_id,
                        source_sha256=source.source_sha256,
                        key=key,
                        reason=f"agent execution failed: {type(exc).__name__}: {exc}",
                    )
                reason = outcome.selected.abstention_reason or ""
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

            if system_id == "plain_llm":
                context = plain_llm_context(
                    gold.regulation_clause,
                    program=bounded_code_context(
                        source,
                        gold.regulation_clause.text,
                    ),
                )
            elif system_id in RAG_RETRIEVAL_MODES:
                context = rag_baseline_context(
                    system_id,
                    gold.regulation_clause.text,
                    program=bounded_code_context(
                        source,
                        gold.regulation_clause.text,
                    ),
                    search=regulation_search,
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
        run_rows,
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
        "--provider",
        choices=PROVIDER_IDS,
        default="ollama",
        help="live model provider; defaults to the local, credential-free Ollama",
    )
    parser.add_argument(
        "--model",
        help="one pinned model used for all selected systems",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        help=(
            "run the seeded, one-per-drift-class config-2 sample into "
            "separate smoke artifacts; N must be 7"
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help=(
            f"predeclared config-2 smoke seed; the frozen value is {CONFIG2_SMOKE_SEED}"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    model_id = args.model or DEFAULT_MODEL_IDS[args.provider]
    rows = load_split()
    search = RegulationSearch()
    entailer = default_entailer()
    systems = SYSTEM_IDS if args.system == "all" else (args.system,)
    for system_id in systems:
        records = run_live_system(
            system_id,
            rows=rows,
            model_id=model_id,
            provider=args.provider,
            smoke_seed=args.seed,
            regulation_search=search,
            entailer=entailer,
            smoke=args.smoke,
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
