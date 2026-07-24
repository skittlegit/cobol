"""Gold-hidden orchestration primitives for T4.1."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.agent.policy import HUNT_REGISTRY, HuntOutcome
from cobol_archaeologist.agent.trajectory import BudgetSpec
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.prompt import DecisionModel
from cobol_archaeologist.model.verify import Entailer
from cobol_archaeologist.schemas import DriftInstance, RegulationClause
from cobol_archaeologist.tool_types import ToolLayer


class SystemContext(BaseModel):
    """The complete benchmark context visible to the system under test."""

    model_config = ConfigDict(extra="forbid")

    clause: RegulationClause
    program_scope: str
    question: str


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: str
    provider: str = ""
    model_id: str
    decoding: dict = Field(default_factory=dict)
    budgets: dict = Field(default_factory=dict)
    repository_commit: str
    input_revision: str = ""
    tool_version: str = ""
    prompt_version: str
    split_path: str
    split_sha256: str = ""
    total: int
    completed_run_keys: list[str] = Field(default_factory=list)
    infrastructure_failures: dict[str, str] = Field(default_factory=dict)


def build_system_context(gold: DriftInstance) -> SystemContext:
    program_scope = Path(gold.provenance.base_program).stem
    return SystemContext(
        clause=gold.regulation_clause,
        program_scope=program_scope,
        question=(
            "Investigate whether the supplied program complies with "
            f"{gold.regulation_clause.doc} {gold.regulation_clause.clause_id}."
        ),
    )


def repository_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def run_key(
    *,
    instance_id: str,
    source_sha256: str,
    system_id: str,
    model_id: str,
    budgets: dict,
    prompt_version: str,
    tool_version: str,
    commit: str,
) -> str:
    payload = json.dumps(
        {
            "instance_id": instance_id,
            "source_sha256": source_sha256,
            "system_id": system_id,
            "model_id": model_id,
            "budgets": budgets,
            "prompt_version": prompt_version,
            "tool_version": tool_version,
            "commit": commit,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def investigate_all_hunts(
    context: SystemContext,
    *,
    tools: ToolLayer,
    model_factory: Callable[[], DecisionModel],
    budget: BudgetSpec | None = None,
    entailer: Entailer | None = None,
) -> HuntOutcome:
    """Run every registered class hunt without revealing which class is gold."""

    outcomes = []
    for hunt in HUNT_REGISTRY.values():
        outcome = hunt.run(
            clause=context.clause,
            tools=tools,
            model=model_factory(),
            program_scope=context.program_scope,
            budget=budget,
            entailer=entailer,
        )
        reason = outcome.abstention_reason or ""
        if reason.startswith(
            ("model response unavailable:", "verification unavailable;")
        ):
            raise RuntimeError(reason)
        outcomes.append(outcome)
    findings = [outcome for outcome in outcomes if not outcome.abstained]
    if findings:
        return max(
            findings,
            key=lambda outcome: (
                outcome.confidence or 0.0,
                -int(outcome.verification_tier),
                outcome.hunt,
            ),
        )
    return outcomes[0]


def record_outcome(
    gold: DriftInstance,
    outcome: HuntOutcome,
    *,
    system_id: str,
    source_sha256: str,
    key: str,
) -> EvaluationRecord:
    return EvaluationRecord(
        instance_id=gold.instance_id,
        gold=gold,
        prediction=outcome.finding,
        confidence=outcome.confidence,
        verification=outcome.verification,
        trajectory=outcome.trajectory,
        abstained=outcome.abstained,
        abstention_reason=outcome.abstention_reason,
        system_id=system_id,
        source_sha256=source_sha256,
        run_key=key,
    )


def infrastructure_failure(
    gold: DriftInstance,
    *,
    system_id: str,
    source_sha256: str,
    key: str,
    reason: str,
) -> EvaluationRecord:
    return EvaluationRecord(
        instance_id=gold.instance_id,
        gold=gold,
        abstained=False,
        infrastructure_error=reason,
        system_id=system_id,
        source_sha256=source_sha256,
        run_key=key,
    )


class EvaluationRunner:
    """Append-only, run-key-resumable evaluation record writer."""

    def __init__(self, records_path: Path, manifest_path: Path) -> None:
        self.records_path = Path(records_path)
        self.manifest_path = Path(manifest_path)

    def _existing(self) -> dict[str, EvaluationRecord]:
        if not self.records_path.exists():
            return {}
        records = [
            EvaluationRecord.model_validate_json(line)
            for line in self.records_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_key = {record.run_key: record for record in records}
        if len(by_key) != len(records):
            raise ValueError("evaluation artifact contains duplicate run keys")
        return by_key

    def run(
        self,
        gold_rows: Iterable[DriftInstance],
        *,
        manifest: RunManifest,
        key_factory: Callable[[DriftInstance], str],
        executor: Callable[[DriftInstance, SystemContext, str], EvaluationRecord],
    ) -> list[EvaluationRecord]:
        rows = list(gold_rows)
        if manifest.total != len(rows):
            raise ValueError("manifest total does not match requested rows")
        existing = self._existing()
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        completed = list(existing.values())
        with self.records_path.open("a", encoding="utf-8", newline="\n") as stream:
            for gold in rows:
                key = key_factory(gold)
                if key in existing:
                    continue
                record = executor(gold, build_system_context(gold), key)
                if record.run_key != key:
                    raise ValueError("executor returned a mismatched run key")
                stream.write(record.model_dump_json() + "\n")
                stream.flush()
                existing[key] = record
                completed.append(record)
        manifest.completed_run_keys = sorted(existing)
        manifest.infrastructure_failures = {
            record.instance_id: record.infrastructure_error
            for record in completed
            if record.infrastructure_error
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return completed
