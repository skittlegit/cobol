"""Run the detector or the baseline over a benchmark split.

    python -m cobol_archaeologist.eval.runner detector --split dev
    python -m cobol_archaeologist.eval.runner rag_reranker --split test

Results go to ``data/eval/<split>/<system>.jsonl`` (one ``EvaluationRecord``
per line).  A run is resumable: a row whose stored ``run_key`` matches the
current method identity is kept, every other row is (re)run.  A new detector
version therefore replaces the old results in place; there is one result file
per split and system.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

from cobol_archaeologist.eval import baselines, codex, detector
from cobol_archaeologist.eval.materialize import (
    MaterializedSource,
    materialize,
    materialize_base,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.verify import Entailer, default_entailer
from cobol_archaeologist.schemas import DriftInstance
from cobol_archaeologist.tools import RealToolLayer

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "data" / "benchmark"
EVAL_ROOT = ROOT / "data" / "eval"
TEMPORAL_PROGRAMS = BENCHMARK / "temporal" / "programs"

SystemID = Literal["detector", "rag_reranker"]
Split = Literal["train", "dev", "test", "temporal"]
SYSTEMS: tuple[SystemID, ...] = ("detector", "rag_reranker")
SPLITS: tuple[Split, ...] = ("train", "dev", "test", "temporal")
FIRST_ALIAS = 900_000


def split_path(split: Split) -> Path:
    if split == "temporal":
        return BENCHMARK / "temporal" / "rows.jsonl"
    return BENCHMARK / f"{split}.jsonl"


def load_split(split: Split) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in split_path(split).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def materialize_row(row: DriftInstance, split: Split) -> MaterializedSource:
    if split == "temporal":
        return materialize_base(row, programs_root=TEMPORAL_PROGRAMS)
    return materialize(row)


def results_path(split: Split, system: SystemID) -> Path:
    return EVAL_ROOT / split / f"{system}.jsonl"


def method_identity(system: SystemID, runtime: str) -> dict[str, str]:
    return {
        "system": system,
        "prompt_version": (
            detector.PROMPT_VERSION
            if system == "detector"
            else baselines.PROMPT_VERSION
        ),
        "model": codex.MODEL_ID,
        "effort": codex.REASONING_EFFORT,
        "runtime": runtime,
    }


def run_key(identity: dict[str, str], row: DriftInstance, source_sha256: str) -> str:
    payload = {**identity, "instance_id": row.instance_id, "source": source_sha256}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def infrastructure_failure(
    row: DriftInstance, *, system: str, source_sha256: str, key: str, reason: str
) -> EvaluationRecord:
    return EvaluationRecord(
        instance_id=row.instance_id,
        gold=row,
        abstained=False,
        infrastructure_error=reason[:4000],
        system_id=system,
        source_sha256=source_sha256,
        run_key=key,
    )


def _host_tools(source: MaterializedSource, directory: Path) -> RealToolLayer:
    source.write_to(directory)
    return RealToolLayer(corpus_root=directory, copybook_paths=[directory])


def program_scope(row: DriftInstance) -> str:
    return Path(row.provenance.base_program).stem


# --------------------------------------------------------------------------
# One case / one batch
# --------------------------------------------------------------------------


def run_detector_case(
    row: DriftInstance,
    source: MaterializedSource,
    *,
    key: str,
    support_root: str,
    entailer: Entailer,
) -> EvaluationRecord:
    alias = f"drift_{FIRST_ALIAS:06d}"
    scope = program_scope(row)
    prompt = detector.build_prompt(
        alias=alias,
        clause=row.regulation_clause,
        program_scope=scope,
        tool_command=codex.bridge_command(support_root),
    )
    result = codex.execute_task(
        prompt=prompt,
        schema=codex.strict_schema(detector.DetectorEnvelope),
        sources={alias: source},
        support_root=support_root,
        descriptor={
            alias: {
                "clause": row.regulation_clause.model_dump(mode="json"),
                "program_scope": scope,
            }
        },
    )
    envelope = detector.DetectorEnvelope.model_validate_json(result.final_message)
    submitted = envelope.results[0]
    if submitted.alias != alias:
        raise ValueError(
            f"response names alias {submitted.alias!r}, expected {alias!r}"
        )
    with tempfile.TemporaryDirectory(prefix="detector-verify-") as temp:
        outcome = detector.finalize_case(
            submitted,
            clause=row.regulation_clause,
            program_scope=scope,
            instance_id=row.instance_id,
            logs=result.tool_logs,
            tools=_host_tools(source, Path(temp)),
            entailer=entailer,
            token_count=result.usage.total_tokens,
            model_id=codex.MODEL_ID,
        )
    return EvaluationRecord(
        instance_id=row.instance_id,
        gold=row,
        prediction=outcome.finding,
        confidence=outcome.confidence,
        verification=outcome.verification,
        trajectory=outcome.trajectory,
        abstained=outcome.abstained,
        abstention_reason=outcome.abstention_reason,
        system_id="detector",
        source_sha256=source.source_sha256,
        run_key=key,
    )


def run_baseline_batch(
    rows: Sequence[DriftInstance],
    sources: dict[str, MaterializedSource],
    keys: dict[str, str],
    *,
    contexts: dict[str, baselines.RAGContext],
    entailer: Entailer,
) -> list[EvaluationRecord]:
    aliases = {
        f"drift_{FIRST_ALIAS + index:06d}": row for index, row in enumerate(rows)
    }
    prompt = baselines.build_prompt(
        [
            {
                "alias": alias,
                "context": contexts[row.instance_id].model_dump(mode="json"),
            }
            for alias, row in aliases.items()
        ]
    )
    result = codex.execute_task(
        prompt=prompt,
        schema=codex.strict_schema(baselines.BaselineEnvelope),
        sources={},
        support_root=None,
    )
    envelope = baselines.BaselineEnvelope.model_validate_json(result.final_message)
    by_alias = {case.alias: case for case in envelope.results}
    share = result.usage.total_tokens // max(1, len(rows))
    records: list[EvaluationRecord] = []
    for alias, row in aliases.items():
        source = sources[row.instance_id]
        submitted = by_alias.get(alias)
        if submitted is None:
            records.append(
                infrastructure_failure(
                    row,
                    system="rag_reranker",
                    source_sha256=source.source_sha256,
                    key=keys[row.instance_id],
                    reason=f"response omitted alias {alias}",
                )
            )
            continue
        with tempfile.TemporaryDirectory(prefix="baseline-verify-") as temp:
            records.append(
                baselines.finalize_case(
                    submitted,
                    gold=row,
                    context=contexts[row.instance_id],
                    tools=_host_tools(source, Path(temp)),
                    entailer=entailer,
                    source_sha256=source.source_sha256,
                    run_key=keys[row.instance_id],
                    token_count=share,
                    model_id=codex.MODEL_ID,
                )
            )
    return records


# --------------------------------------------------------------------------
# Whole split
# --------------------------------------------------------------------------


def _load_existing(path: Path) -> dict[str, EvaluationRecord]:
    if not path.exists():
        return {}
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = EvaluationRecord.model_validate_json(line)
            records[record.instance_id] = record
    return records


def _write_all(
    path: Path, records: dict[str, EvaluationRecord], order: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for instance_id in order:
            if instance_id in records:
                stream.write(records[instance_id].model_dump_json() + "\n")
    temporary.replace(path)


def run_split(
    system: SystemID,
    split: Split,
    *,
    ids: Sequence[str] | None = None,
    workers: int = 3,
    retry_failures: bool = True,
    progress: Callable[[str], None] = print,
) -> list[EvaluationRecord]:
    rows = load_split(split)
    if ids:
        wanted = set(ids)
        rows = [row for row in rows if row.instance_id in wanted]
        missing = wanted - {row.instance_id for row in rows}
        if missing:
            raise ValueError(f"unknown instance ids for {split}: {sorted(missing)}")
    codex.check_login()
    support_root, runtime = codex.prepare_support_runtime()
    identity = method_identity(system, runtime)
    sources = {row.instance_id: materialize_row(row, split) for row in rows}
    keys = {
        row.instance_id: run_key(identity, row, sources[row.instance_id].source_sha256)
        for row in rows
    }
    path = results_path(split, system)
    all_rows = load_split(split)
    order = [row.instance_id for row in all_rows]
    stored = _load_existing(path)
    # Rows outside this run keep their stored record; rows in it are kept only
    # when they belong to the current method and did not fail on infrastructure.
    pending = [
        row
        for row in rows
        if not (
            row.instance_id in stored
            and stored[row.instance_id].run_key == keys[row.instance_id]
            and not (retry_failures and stored[row.instance_id].infrastructure_error)
        )
    ]
    progress(
        f"{system}/{split}: {len(rows) - len(pending)} current, {len(pending)} to run"
    )
    entailer = default_entailer()
    lock = threading.Lock()
    stop = threading.Event()
    done = 0

    def save(record: EvaluationRecord) -> None:
        nonlocal done
        with lock:
            stored[record.instance_id] = record
            _write_all(path, stored, order)
            done += 1
            outcome = (
                "INFRA"
                if record.infrastructure_error
                else "ABSTAIN"
                if record.abstained
                else record.prediction.drift_type
            )
            progress(
                f"[{done}/{len(pending)}] {record.instance_id} "
                f"gold={record.gold.drift_type} -> {outcome}"
            )

    if system == "detector":

        def work(row: DriftInstance) -> EvaluationRecord:
            source = sources[row.instance_id]
            if stop.is_set():
                return None
            try:
                return run_detector_case(
                    row,
                    source,
                    key=keys[row.instance_id],
                    support_root=support_root,
                    entailer=entailer,
                )
            except codex.CodexAuthError:
                stop.set()
                raise
            except Exception as exc:  # noqa: BLE001
                return infrastructure_failure(
                    row,
                    system="detector",
                    source_sha256=source.source_sha256,
                    key=keys[row.instance_id],
                    reason=f"{type(exc).__name__}: {exc}",
                )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(work, row) for row in pending]):
                record = future.result()
                if record is not None:
                    save(record)
    else:
        from cobol_archaeologist.rag.search import RegulationSearch

        search = RegulationSearch(mode="hybrid_rerank")
        contexts = {
            row.instance_id: baselines.build_context(
                row, sources[row.instance_id], search
            )
            for row in pending
        }
        batches = [
            pending[index : index + baselines.BATCH_SIZE]
            for index in range(0, len(pending), baselines.BATCH_SIZE)
        ]

        def work_batch(batch: list[DriftInstance]) -> list[EvaluationRecord]:
            if stop.is_set():
                return []
            try:
                return run_baseline_batch(
                    batch, sources, keys, contexts=contexts, entailer=entailer
                )
            except codex.CodexAuthError:
                stop.set()
                raise
            except Exception as exc:  # noqa: BLE001
                return [
                    infrastructure_failure(
                        row,
                        system="rag_reranker",
                        source_sha256=sources[row.instance_id].source_sha256,
                        key=keys[row.instance_id],
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                    for row in batch
                ]

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(work_batch, b) for b in batches]):
                for record in future.result():
                    save(record)
    final = _load_existing(path)
    return [final[row.instance_id] for row in rows if row.instance_id in final]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("system", choices=SYSTEMS)
    parser.add_argument("--split", choices=SPLITS, required=True)
    parser.add_argument("--ids", nargs="*", help="run only these instance ids")
    parser.add_argument(
        "--ids-file", type=Path, help="file with one instance id per line"
    )
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    ids = list(args.ids or [])
    if args.ids_file:
        ids += [
            line.strip()
            for line in args.ids_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    run_split(args.system, args.split, ids=ids or None, workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
