"""Frozen, resumable configuration-3 execution through isolated Luna tasks."""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.adaptive import (
    ADAPTIVE_SYSTEM_PROMPT,
    CONFIG3_AGENT_BUDGET,
    AdaptiveOutcome,
    EvidenceLedgerEntry,
    validate_evidence_ledger,
)
from cobol_archaeologist.agent.policy import confidence_for_tier, get_hunt
from cobol_archaeologist.agent.trajectory import BudgetSpec, ToolCall, Trajectory
from cobol_archaeologist.eval.codex_batch import (
    AGENT_HUNTS,
    CodexBaselineEnvelope,
    CodexBatchEnvelope,
    SubmittedResponse,
    bind_submitted_response,
    strict_codex_schema,
)
from cobol_archaeologist.eval.codex_live import (
    DEFAULT_CODEX_BINARY,
    DEFAULT_SUPPORT_BASE,
    DEFAULT_WSL_DISTRO,
    CodexTaskExecution,
    _check_chatgpt_login,
    _require_ok,
    _tool_layer,
    _wsl,
    _wsl_chatgpt_account_sha256,
    batch_size_for,
    build_agent_prompt,
    build_baseline_prompt,
    codex_exec_arguments,
    codex_request_sha256,
    execute_codex_task,
    prepare_support_runtime,
)
from cobol_archaeologist.eval.codex_tool import ADAPTIVE_HUNT, ToolLogEntry
from cobol_archaeologist.eval.collaboration_staging import (
    StagedCollaborationTask,
    load_staged_tool_logs,
    stage_collaboration_task,
    tool_log_entry_sha256,
)
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationGroupIdentity,
    CollaborationSubagentExecution,
    CollaborationSubagentExecutionV2,
    build_collaboration_request,
    collaboration_tool_log_sha256,
    collaboration_tool_receipt_payload,
    ensure_collaboration_request,
    load_collaboration_bundle,
)
from cobol_archaeologist.eval.live import AGENT_BUDGET, BASELINE_BUDGET
from cobol_archaeologist.eval.materialize import (
    MaterializedSource,
    materialize,
    materialize_base,
)
from cobol_archaeologist.eval.metrics import detection
from cobol_archaeologist.eval.phase5_headline import (
    _balanced_accuracy_structured,
    paired_f1_comparison,
)
from cobol_archaeologist.eval.run import repository_commit
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.prompt import AgentResponse
from cobol_archaeologist.model.verify import (
    Entailer,
    Finding,
    default_entailer,
    verify,
)
from cobol_archaeologist.schemas import DriftInstance, RegulationClause
from cobol_archaeologist.tool_types import ToolLayer

ROOT = Path(__file__).resolve().parents[3]
MODEL_ID = "gpt-5.6-luna"
REASONING_EFFORT = "max"
PROVIDER_ID = "collaboration_subagent"
AUTHENTICATION = "in_product_orchestration"
LEGACY_PROVIDER_ID = "chatgpt-codex"
LEGACY_AUTHENTICATION = "ChatGPT"
PROMPT_VERSION = "m4-config3-adaptive-v1"
ADAPTIVE_BATCH_SIZE = 1
DEFAULT_MAX_WORKERS = 3
CONFIG3_SMOKE_SEED = 20_260_824
DEV_SPLIT = ROOT / "data" / "benchmark" / "v1" / "dev.jsonl"
TEST_SPLIT = ROOT / "data" / "benchmark" / "v1" / "test.jsonl"
OUTPUT_DIR = ROOT / "data" / "eval" / "m4-config3"
FREEZE_PATH = OUTPUT_DIR / "run-freeze.json"
COLLABORATION_FREEZE_PATH = OUTPUT_DIR / "run-freeze-v2.json"
DEVELOPMENT_SMOKE_PATH = OUTPUT_DIR / "development-smoke.json"
COLLABORATION_STAGED_REQUEST_DIRECTORY = "requests-v3"
COLLABORATION_STAGING_DIRECTORY = "task-staging-v1"
T6_V2_MANIFEST = ROOT / "data" / "benchmark" / "t6-v2" / "final" / "manifest.json"
PHASE5_BASELINE_PATHS: tuple[Path, ...] = (
    Path("data/eval/m5/baselines/train_majority.jsonl"),
    Path("data/eval/m5/baselines/train_majority.manifest.json"),
    Path("data/eval/m5/baselines/prevalence_random.jsonl"),
    Path("data/eval/m5/baselines/prevalence_random.manifest.json"),
    Path("data/eval/m5/baselines/static_keyword.jsonl"),
    Path("data/eval/m5/baselines/static_keyword.manifest.json"),
    Path("data/eval/m5/baselines/attacker_with_bases.jsonl"),
    Path("data/eval/m5/baselines/attacker_with_bases.manifest.json"),
)
PHASE5_AGGREGATE_PATHS: tuple[Path, ...] = (
    Path("data/eval/m5/error-analysis.json"),
    Path("data/eval/m5/report.json"),
    Path("data/eval/m5/t5.3-completion-summary.json"),
)

Config3SystemID = Literal[
    "agent",
    "adaptive_agent",
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
]
CONFIG3_SYSTEMS: tuple[Config3SystemID, ...] = (
    "agent",
    "adaptive_agent",
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
)


class SubmittedAdaptiveCase(BaseModel):
    """One final case-local decision; trusted identity and clause are omitted."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(pattern=r"^drift_9\d{5}$")
    evidence_ledger: list[EvidenceLedgerEntry]
    response: SubmittedResponse


class CodexAdaptiveEnvelope(BaseModel):
    """Batch-size-one wire contract for the proper adaptive agent."""

    model_config = ConfigDict(extra="forbid")

    results: list[SubmittedAdaptiveCase] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def _one_alias(self) -> CodexAdaptiveEnvelope:
        if len({result.alias for result in self.results}) != len(self.results):
            raise ValueError("adaptive response aliases contain duplicates")
        return self


class FinalizedArtifactPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Config3RunFreeze(BaseModel):
    """Complete identity sealed before any official smoke provider call."""

    model_config = ConfigDict(extra="forbid")

    configuration: Literal[3] = 3
    provider: Literal["collaboration_subagent", "chatgpt-codex"] = PROVIDER_ID
    authentication: Literal["in_product_orchestration", "ChatGPT"] = AUTHENTICATION
    model_id: Literal["gpt-5.6-luna"] = MODEL_ID
    reasoning_effort: Literal["max"] = REASONING_EFFORT
    prompt_version: str
    repository_commit: str
    runtime_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    codex_cli_version: str | None = None
    wsl_distribution: str | None = None
    transport: Literal["collaboration_subagent", "wsl", "native"] = (
        "collaboration_subagent"
    )
    codex_binary: str | None = None
    max_workers: int = Field(ge=1)
    systems: tuple[Config3SystemID, ...]
    budgets: dict[str, dict[str, Any]]
    batch_sizes: dict[str, int]
    identity_hashes: dict[str, str]
    phase5_baseline_sha256: dict[str, str]
    phase5_aggregate_sha256: dict[str, str]
    chatgpt_account_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision_bootstrap_resamples: Literal[10_000] = 10_000
    decision_randomization_samples: Literal[20_000] = 20_000
    decision_statistics_seed: Literal[20_260_823] = 20_260_823
    dev_split_path: str
    dev_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    train_split_path: str
    train_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_split_path: str
    test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    t6_v2_path: str
    t6_v2_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    smoke_seed: int
    smoke_instance_ids: tuple[str, ...] = Field(min_length=14, max_length=14)
    dev_order: tuple[str, ...]
    test_order: tuple[str, ...]
    t6_order: tuple[str, ...]
    t6_source_inputs: dict[str, FinalizedArtifactPin]
    source_sha256: dict[str, str]

    @model_validator(mode="after")
    def _transport_identity_is_explicit(self) -> Config3RunFreeze:
        if self.transport == "collaboration_subagent":
            if (
                self.provider != "collaboration_subagent"
                or self.authentication != "in_product_orchestration"
            ):
                raise ValueError(
                    "collaboration_subagent must not be labeled as ChatGPT Codex"
                )
        elif (
            self.provider != LEGACY_PROVIDER_ID
            or self.authentication != LEGACY_AUTHENTICATION
            or self.chatgpt_account_sha256 is None
            or not self.codex_cli_version
            or not self.wsl_distribution
            or not self.codex_binary
        ):
            raise ValueError("legacy native/WSL transport requires its Codex identity")
        return self


class DevelopmentSmokeRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    drift_type: str
    source_split: Literal["dev", "train"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DevelopmentSmokeFreeze(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    seed: int
    selection: str
    dev_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    train_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: list[DevelopmentSmokeRow] = Field(min_length=14, max_length=14)
    hidden_test_rows: Literal[0]


class FinalizedReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_primary_metadata: FinalizedArtifactPin
    ai_primary_responses: FinalizedArtifactPin
    ai_primary_audit_manifest: FinalizedArtifactPin
    independent_verifier_metadata: FinalizedArtifactPin
    independent_verifier_responses: FinalizedArtifactPin
    adjudication_metadata: FinalizedArtifactPin
    adjudication_responses: FinalizedArtifactPin
    ai_adjudication_audit_manifest: FinalizedArtifactPin | None
    ai_adjudication_bridge_manifest: FinalizedArtifactPin | None
    independent_verifier_audit_manifest: FinalizedArtifactPin
    pair_correction_audit_manifest: FinalizedArtifactPin | None = None
    pair_correction_bridge_manifest: FinalizedArtifactPin | None = None
    pair_correction_responses: FinalizedArtifactPin | None = None
    replacement_audit_manifest: FinalizedArtifactPin | None = None
    replacement_bridge_manifest: FinalizedArtifactPin | None = None
    replacement_plan: FinalizedArtifactPin | None = None
    replacement_responses: FinalizedArtifactPin | None = None


class FinalizedT6Manifest(BaseModel):
    """Narrow protocol consumed by the official temporal freeze."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    finalized: Literal[True]
    evaluation_ready: Literal[True]
    target_pair_count: Literal[20]
    evaluation_side_count: Literal[40]
    evaluation_rows: FinalizedArtifactPin
    pair_order: tuple[str, ...] = Field(min_length=20, max_length=20)
    instance_order: tuple[str, ...] = Field(min_length=40, max_length=40)
    pair_members: dict[str, tuple[str, str]]
    authority_targets: dict[
        str,
        Literal[
            "grievance_response_deadline",
            "partnership_beneficial_owner_threshold",
            "central_kyc_update_deadline",
        ],
    ]
    source_inputs: dict[str, FinalizedArtifactPin]
    preparation_manifest: FinalizedArtifactPin
    promotion_report: FinalizedArtifactPin
    review_evidence: FinalizedReviewEvidence
    controlled_ai_primary_verified: Literal[True]

    @model_validator(mode="after")
    def _unique_orders(self) -> FinalizedT6Manifest:
        if len(set(self.pair_order)) != 20:
            raise ValueError("finalized T6 pair order must be unique")
        if len(set(self.instance_order)) != 40:
            raise ValueError("finalized T6 instance order must be unique")
        if tuple(self.pair_members) != self.pair_order:
            raise ValueError("finalized T6 pair_members order differs from pair_order")
        if tuple(self.authority_targets) != self.pair_order:
            raise ValueError("finalized T6 authority_targets differ from pair_order")
        flattened = tuple(
            instance_id
            for pair_id in self.pair_order
            for instance_id in self.pair_members[pair_id]
        )
        if flattened != self.instance_order:
            raise ValueError("finalized T6 pair_members differ from instance_order")
        return self


def _validate_finalized_pin(root: Path, pin: FinalizedArtifactPin) -> Path:
    path = (root / pin.path).resolve()
    if root != path and root not in path.parents:
        raise ValueError("finalized T6 artifact pin escapes the repository")
    if hashlib.sha256(path.read_bytes()).hexdigest() != pin.sha256:
        raise ValueError(f"finalized T6 artifact pin changed: {pin.path}")
    return path


def load_finalized_t6_rows(
    *, root: Path, manifest_path: Path
) -> tuple[FinalizedT6Manifest, list[DriftInstance]]:
    """Load and validate the promoted 40-side artifact, never raw booleans."""

    root = Path(root).resolve()
    manifest = FinalizedT6Manifest.model_validate_json(
        Path(manifest_path).read_text(encoding="utf-8")
    )
    immutable_pins = [
        manifest.preparation_manifest,
        manifest.promotion_report,
        *manifest.review_evidence.model_dump().values(),
    ]
    for pin in (item for item in immutable_pins if item is not None):
        _validate_finalized_pin(root, FinalizedArtifactPin.model_validate(pin))
    from cobol_archaeologist.benchmark.t6_review import (
        ReviewEvidencePins,
        T6ReviewPromotionReport,
        build_t6_review_promotion,
    )

    promotion_path = _validate_finalized_pin(root, manifest.promotion_report)
    promotion = T6ReviewPromotionReport.model_validate_json(
        promotion_path.read_text(encoding="utf-8")
    )
    preparation_path = _validate_finalized_pin(root, manifest.preparation_manifest)
    replayed_promotion = build_t6_review_promotion(
        root=root,
        manifest_path=preparation_path,
        evidence=ReviewEvidencePins(
            ai_primary=manifest.review_evidence.ai_primary_metadata.model_dump(
                mode="json"
            ),
            independent_verifier=manifest.review_evidence.independent_verifier_metadata.model_dump(
                mode="json"
            ),
            adjudication=manifest.review_evidence.adjudication_metadata.model_dump(
                mode="json"
            ),
            ai_adjudication_bridge_manifest=(
                manifest.review_evidence.ai_adjudication_bridge_manifest.model_dump(
                    mode="json"
                )
                if manifest.review_evidence.ai_adjudication_bridge_manifest is not None
                else None
            ),
            pair_correction_bridge_manifest=(
                manifest.review_evidence.pair_correction_bridge_manifest.model_dump(
                    mode="json"
                )
                if manifest.review_evidence.pair_correction_bridge_manifest is not None
                else None
            ),
            replacement_bridge_manifest=(
                manifest.review_evidence.replacement_bridge_manifest.model_dump(
                    mode="json"
                )
                if manifest.review_evidence.replacement_bridge_manifest is not None
                else None
            ),
        ),
    )
    if (
        replayed_promotion.model_dump(mode="json") != promotion.model_dump(mode="json")
        or not promotion.evaluation_ready
        or not promotion.controlled_ai_primary_verified
        or tuple(promotion.proposed_pair_order) != manifest.pair_order
        or tuple(promotion.proposed_instance_order) != manifest.instance_order
        or {key: tuple(value) for key, value in promotion.proposed_pair_members.items()}
        != manifest.pair_members
        or promotion.proposed_authority_targets != manifest.authority_targets
        or promotion.review_evidence.model_dump(mode="json")
        != manifest.review_evidence.model_dump(mode="json")
        or {
            key: value.model_dump(mode="json")
            for key, value in promotion.proposed_source_inputs.items()
        }
        != {
            key: value.model_dump(mode="json")
            for key, value in manifest.source_inputs.items()
        }
    ):
        raise ValueError("finalized T6 manifest differs from successful promotion")
    rows_path = _validate_finalized_pin(root, manifest.evaluation_rows)
    payload = rows_path.read_bytes()
    rows = [
        DriftInstance.model_validate_json(line)
        for line in payload.decode("utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 40 or len({row.instance_id for row in rows}) != 40:
        raise ValueError("finalized T6 must contain exactly 40 unique side instances")
    if tuple(row.instance_id for row in rows) != manifest.instance_order:
        raise ValueError("finalized T6 evaluation_rows differs from instance_order")
    if set(manifest.source_inputs) != {row.instance_id for row in rows}:
        raise ValueError("finalized T6 source_inputs must exactly cover all 40 sides")
    materialized: dict[str, MaterializedSource] = {}
    for row in rows:
        pin = manifest.source_inputs[row.instance_id]
        source_path = _validate_finalized_pin(root, pin)
        if source_path.name != Path(row.provenance.base_program).name:
            raise ValueError("finalized T6 source input differs from base_program")
        materialized[row.instance_id] = materialize_base(
            row, programs_root=source_path.parent
        )
    rows_by_id = {row.instance_id: row for row in rows}
    for pair_id in manifest.pair_order:
        pair = [rows_by_id[item] for item in manifest.pair_members[pair_id]]
        left, right = pair
        if left.regulation_clause.version == right.regulation_clause.version:
            raise ValueError("finalized T6 pair must span distinct versions")
        if (
            left.regulation_clause.effective_date
            == right.regulation_clause.effective_date
        ):
            raise ValueError("finalized T6 pair must span distinct effective dates")
        if left.code_locus != right.code_locus:
            raise ValueError("finalized T6 pair must share an identical code locus")
        if {row.drift_type == "D7_conformant" for row in pair} != {False, True}:
            raise ValueError("each finalized T6 pair must contain D7 and drift sides")
        source_hashes = {materialized[row.instance_id].source_sha256 for row in pair}
        if len(source_hashes) != 1:
            raise ValueError("each finalized T6 pair must share identical source code")
        haystacks = [
            (
                f"{row.regulation_clause.doc} {row.regulation_clause.clause_id} "
                f"{row.regulation_clause.text}"
            ).lower()
            for row in pair
        ]
        target = manifest.authority_targets[pair_id]
        target_matches = {
            "grievance_response_deadline": lambda text: (
                "complain" in text or "ombudsman" in text
            ),
            "partnership_beneficial_owner_threshold": lambda text: (
                "beneficial owner" in text or "partnership" in text
            ),
            "central_kyc_update_deadline": lambda text: (
                "registry" in text
                or "central kyc" in text
                or "ckycr" in text
                or ("kyc" in text and "upload" in text)
            ),
        }
        if not all(target_matches[target](text) for text in haystacks):
            raise ValueError("finalized T6 authority target differs from pair rows")
    return manifest, rows


def materialize_finalized_t6_row(
    row: DriftInstance,
    *,
    root: Path,
    source_inputs: Mapping[str, FinalizedArtifactPin],
) -> MaterializedSource:
    pin = source_inputs.get(row.instance_id)
    if pin is None:
        raise ValueError(f"no finalized T6 source input for {row.instance_id}")
    source_path = (Path(root).resolve() / pin.path).resolve()
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != pin.sha256:
        raise ValueError(f"finalized T6 source input changed for {row.instance_id}")
    return materialize_base(row, programs_root=source_path.parent)


class Config3Progress(BaseModel):
    """Crash-safe coordinator state; transient access failures stay pending."""

    model_config = ConfigDict(extra="forbid")

    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_id: Config3SystemID
    run_mode: Literal["smoke", "full", "temporal"]
    completed_run_keys: list[str]
    pending_instance_ids: list[str]
    interruptions: dict[str, str]
    status: Literal["IN_PROGRESS", "VALID", "NOT_EVALUABLE"]


class ExecutionBundleMarker(BaseModel):
    """Completion marker binding the key, request, events, logs, and payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2"] = "2"
    key: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_stream_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_logs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RecordSidecarMarker(BaseModel):
    """Bind a finalized record to the exact raw execution that produced it."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2"] = "2"
    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_bundle_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_execution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Config3SmokeReadiness(BaseModel):
    """Global all-system gate required before any hidden-test call."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    systems: tuple[Config3SystemID, ...]
    progress_sha256: dict[str, str]
    status: Literal["VALID"] = "VALID"


class TemporalPairScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str
    instance_ids: tuple[str, str]
    authority_target: str
    side_correct: tuple[bool, bool]
    pair_correct: bool


class Config3TemporalScore(BaseModel):
    """Pinned paired scoring over the finalized 20-pair temporal roster."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["config3-temporal-score-v1"] = "config3-temporal-score-v1"
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    finalized_t6_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pair_order: tuple[str, ...] = Field(min_length=20, max_length=20)
    pairs: tuple[TemporalPairScore, ...] = Field(min_length=20, max_length=20)
    paired_correct: int = Field(ge=0, le=20)
    paired_accuracy: float = Field(ge=0.0, le=1.0)
    status: Literal["VALID"] = "VALID"

    @model_validator(mode="after")
    def _pairing_is_exact(self) -> Config3TemporalScore:
        if tuple(pair.pair_id for pair in self.pairs) != self.pair_order:
            raise ValueError("temporal score pairs differ from pinned pair_order")
        flattened = [item for pair in self.pairs for item in pair.instance_ids]
        if len(set(flattened)) != 40:
            raise ValueError("temporal score must cover 40 unique side instances")
        correct = sum(pair.pair_correct for pair in self.pairs)
        if correct != self.paired_correct or self.paired_accuracy != correct / 20:
            raise ValueError("temporal score totals differ from pair outcomes")
        if any(pair.pair_correct != all(pair.side_correct) for pair in self.pairs):
            raise ValueError("temporal pair correctness differs from its sides")
        return self


class Configuration3DecisionArtifact(BaseModel):
    """Exact migration-facing release decision contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-decision-v1"] = (
        "configuration-3-decision-v1"
    )
    configuration: Literal[3] = 3
    status: Literal["GO", "NO_GO", "NOT_EVALUABLE"]


class Config3InterproceduralComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    paired_rows: int = Field(gt=0)
    adaptive_f1: float = Field(ge=0.0, le=1.0)
    rag_reranker_f1: float = Field(ge=0.0, le=1.0)
    delta_f1: float = Field(ge=-1.0, le=1.0)
    bootstrap_95_ci: tuple[float, float]
    paired_randomization_p: float = Field(ge=0.0, le=1.0)


class Config3QualityMetrics(BaseModel):
    """Hash-bound T8.1 release-utility evidence derived from frozen outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-quality-v1"] = "configuration-3-quality-v1"
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adaptive_records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rag_reranker_records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_score_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_resamples: Literal[10_000]
    randomization_samples: Literal[20_000]
    statistics_seed: Literal[20_260_823]
    t1_f1: float = Field(ge=0.0, le=1.0)
    balanced_accuracy: float = Field(ge=0.0, le=1.0)
    answer_rate: float = Field(ge=0.0, le=1.0)
    answered_accuracy: float = Field(ge=0.0, le=1.0)
    interprocedural: Config3InterproceduralComparison
    temporal_pair_count: Literal[20]
    temporal_paired_accuracy: float = Field(ge=0.0, le=1.0)
    unverified_emissions: Literal[0]
    evidence_threshold_relaxed: Literal[False]
    gates: dict[str, bool]
    all_gates_pass: bool
    status: Literal["VALID"] = "VALID"

    @model_validator(mode="after")
    def _gates_are_exact(self) -> Config3QualityMetrics:
        expected = {
            "t1_f1": self.t1_f1 >= 0.70,
            "balanced_accuracy": self.balanced_accuracy >= 0.65,
            "answer_rate": self.answer_rate >= 0.60,
            "answered_accuracy": self.answered_accuracy >= 0.80,
            "interprocedural_advantage": (
                self.interprocedural.delta_f1 >= 0.10
                and self.interprocedural.bootstrap_95_ci[0] > 0
                and self.interprocedural.paired_randomization_p < 0.05
            ),
            "temporal_paired_accuracy": (
                self.temporal_pair_count >= 20 and self.temporal_paired_accuracy >= 0.70
            ),
            "verified_evidence": (
                self.unverified_emissions == 0 and not self.evidence_threshold_relaxed
            ),
        }
        if self.gates != expected or self.all_gates_pass != all(expected.values()):
            raise ValueError("configuration-3 quality gate results are inconsistent")
        return self


class Configuration3DecisionInputs(BaseModel):
    """Hash-bound evidence used to derive, never select, the decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-decision-inputs-v1"] = (
        "configuration-3-decision-inputs-v1"
    )
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    full_progress_sha256: dict[str, str]
    temporal_score_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    quality_metrics_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    temporal_pair_floor: Literal[0.7] = 0.7
    derived_status: Literal["GO", "NO_GO", "NOT_EVALUABLE"]


def canonical_sha256(value: BaseModel | Mapping[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def runtime_source_sha256(root: Path = ROOT) -> str:
    """Hash the exact support-runtime tree when Git metadata is read-only."""

    root = Path(root)
    paths = [root / "pyproject.toml"]
    paths.extend(sorted((root / "src").rglob("*.py")))
    vendor = root / "vendor" / "tree-sitter-cobol"
    paths.extend(sorted(path for path in vendor.rglob("*") if path.is_file()))
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def chatgpt_account_sha256(identity: str) -> str:
    normalized = identity.strip()
    if len(normalized) < 3:
        raise ValueError("a stable ChatGPT account identity is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_phase5_baseline_identity(
    freeze: Config3RunFreeze, *, root: Path = ROOT
) -> None:
    actual = {
        relative.as_posix(): hashlib.sha256(
            (Path(root) / relative).read_bytes()
        ).hexdigest()
        for relative in PHASE5_BASELINE_PATHS
    }
    if actual != freeze.phase5_baseline_sha256:
        raise RuntimeError(
            "deterministic Phase-5 baseline artifacts differ from freeze"
        )
    aggregates = {
        relative.as_posix(): hashlib.sha256(
            (Path(root) / relative).read_bytes()
        ).hexdigest()
        for relative in PHASE5_AGGREGATE_PATHS
    }
    if aggregates != freeze.phase5_aggregate_sha256:
        raise RuntimeError("Phase-5 aggregate artifacts differ from freeze")


def config3_run_key(
    *,
    freeze: Config3RunFreeze,
    system_id: Config3SystemID,
    run_mode: Literal["smoke", "full", "temporal"],
    instance_id: str,
    source_sha256: str,
) -> str:
    """Bind a result to every frozen identity field through the freeze hash."""

    return canonical_sha256(
        {
            "freeze_sha256": canonical_sha256(freeze),
            "system_id": system_id,
            "run_mode": run_mode,
            "instance_id": instance_id,
            "source_sha256": source_sha256,
        }
    )


def _load_split(path: Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_config3_freeze(
    *,
    repository_commit_value: str,
    codex_cli_version: str | None = None,
    wsl_distribution: str | None = None,
    chatgpt_account_identity: str | None = None,
    transport: Literal["collaboration_subagent", "wsl", "native"] | None = None,
    codex_binary: str | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    root: Path = ROOT,
) -> Config3RunFreeze:
    """Build the complete freeze, refusing an unfinished T6-v2 review set."""

    root = Path(root)
    dev_path = root / DEV_SPLIT.relative_to(ROOT)
    train_path = root / "data" / "benchmark" / "v1" / "train.jsonl"
    test_path = root / TEST_SPLIT.relative_to(ROOT)
    t6_path = root / T6_V2_MANIFEST.relative_to(ROOT)
    try:
        t6_manifest, t6_rows = load_finalized_t6_rows(root=root, manifest_path=t6_path)
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "T6-v2 has no valid finalized 40-side evaluation artifact"
        ) from exc
    dev = _load_split(dev_path)
    train = _load_split(train_path)
    test = _load_split(test_path)
    smoke = seeded_dev_smoke(dev, fallback_rows=train)
    smoke_path = root / DEVELOPMENT_SMOKE_PATH.relative_to(ROOT)
    smoke_freeze = DevelopmentSmokeFreeze.model_validate_json(
        smoke_path.read_text(encoding="utf-8")
    )
    if smoke_freeze.seed != CONFIG3_SMOKE_SEED:
        raise RuntimeError("development smoke seed differs from runner")
    if (
        smoke_freeze.dev_split_sha256
        != hashlib.sha256(dev_path.read_bytes()).hexdigest()
    ):
        raise RuntimeError("development smoke dev hash differs")
    if (
        smoke_freeze.train_split_sha256
        != hashlib.sha256(train_path.read_bytes()).hexdigest()
    ):
        raise RuntimeError("development smoke train hash differs")
    computed_smoke = [
        {
            "instance_id": row.instance_id,
            "drift_type": row.drift_type,
            "source_split": "dev" if row in dev else "train",
            "source_sha256": materialize(row).source_sha256,
        }
        for row in smoke
    ]
    if [row.model_dump(mode="json") for row in smoke_freeze.rows] != computed_smoke:
        raise RuntimeError("committed development smoke roster differs from selector")
    source_rows = [*smoke, *test]
    source_sha = {
        row.instance_id: materialize(row).source_sha256 for row in source_rows
    }
    source_sha.update(
        {
            row.instance_id: materialize_finalized_t6_row(
                row, root=root, source_inputs=t6_manifest.source_inputs
            ).source_sha256
            for row in t6_rows
        }
    )
    t6_order = tuple(row.instance_id for row in t6_rows)
    identity_paths = {
        "adaptive_agent": root
        / "src"
        / "cobol_archaeologist"
        / "agent"
        / "adaptive.py",
        "config3_runner": root
        / "src"
        / "cobol_archaeologist"
        / "eval"
        / "config3_live.py",
        "tool_bridge": root / "src" / "cobol_archaeologist" / "eval" / "codex_tool.py",
        "provider_contract": root
        / "src"
        / "cobol_archaeologist"
        / "eval"
        / "codex_batch.py",
        "verifier": root / "src" / "cobol_archaeologist" / "model" / "verify.py",
        "evidence_policy": root / "src" / "cobol_archaeologist" / "agent" / "policy.py",
    }
    identity_hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in identity_paths.items()
    }
    identity_hashes["adaptive_system_prompt"] = hashlib.sha256(
        ADAPTIVE_SYSTEM_PROMPT.encode("utf-8")
    ).hexdigest()
    phase5_hashes = {}
    for relative in PHASE5_BASELINE_PATHS:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"missing deterministic Phase-5 artifact {relative}")
        phase5_hashes[relative.as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    phase5_aggregates = {
        relative.as_posix(): hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in PHASE5_AGGREGATE_PATHS
    }
    batch_sizes = {
        system: (
            ADAPTIVE_BATCH_SIZE
            if system == "adaptive_agent"
            else batch_size_for(system)
        )
        for system in CONFIG3_SYSTEMS
    }
    budgets = {
        system: (
            CONFIG3_AGENT_BUDGET
            if system == "adaptive_agent"
            else (AGENT_BUDGET if system == "agent" else BASELINE_BUDGET)
        ).model_dump(mode="json")
        for system in CONFIG3_SYSTEMS
    }
    legacy = transport in {"wsl", "native"}
    if legacy and chatgpt_account_identity is None:
        raise ValueError("legacy transport requires a ChatGPT account identity")
    return Config3RunFreeze(
        provider=LEGACY_PROVIDER_ID if legacy else PROVIDER_ID,
        authentication=LEGACY_AUTHENTICATION if legacy else AUTHENTICATION,
        prompt_version=PROMPT_VERSION,
        repository_commit=repository_commit_value,
        runtime_source_sha256=runtime_source_sha256(root),
        codex_cli_version=codex_cli_version,
        wsl_distribution=wsl_distribution,
        transport=transport,
        codex_binary=(codex_binary or DEFAULT_CODEX_BINARY) if legacy else None,
        max_workers=max_workers,
        systems=CONFIG3_SYSTEMS,
        budgets=budgets,
        batch_sizes=batch_sizes,
        identity_hashes=identity_hashes,
        phase5_baseline_sha256=phase5_hashes,
        phase5_aggregate_sha256=phase5_aggregates,
        chatgpt_account_sha256=(
            chatgpt_account_sha256(chatgpt_account_identity)
            if chatgpt_account_identity is not None
            else None
        ),
        dev_split_path=dev_path.relative_to(root).as_posix(),
        dev_split_sha256=hashlib.sha256(dev_path.read_bytes()).hexdigest(),
        train_split_path=train_path.relative_to(root).as_posix(),
        train_split_sha256=hashlib.sha256(train_path.read_bytes()).hexdigest(),
        test_split_path=test_path.relative_to(root).as_posix(),
        test_split_sha256=hashlib.sha256(test_path.read_bytes()).hexdigest(),
        t6_v2_path=t6_path.relative_to(root).as_posix(),
        t6_v2_sha256=hashlib.sha256(t6_path.read_bytes()).hexdigest(),
        smoke_seed=CONFIG3_SMOKE_SEED,
        smoke_instance_ids=tuple(row.instance_id for row in smoke),
        dev_order=tuple(row.instance_id for row in dev),
        test_order=tuple(row.instance_id for row in test),
        t6_order=t6_order,
        t6_source_inputs=t6_manifest.source_inputs,
        source_sha256=source_sha,
    )


def seeded_dev_smoke(
    rows: Sequence[DriftInstance],
    *,
    fallback_rows: Sequence[DriftInstance] = (),
    seed: int = CONFIG3_SMOKE_SEED,
) -> list[DriftInstance]:
    """Select two per class from dev, using frozen train only when absent."""

    selected: list[DriftInstance] = []
    for drift_type in AGENT_HUNTS:
        candidates = sorted(
            (
                row
                for row in rows
                if row.drift_type == drift_type and _can_materialize(row)
            ),
            key=lambda row: row.instance_id,
        )
        if len(candidates) < 2:
            existing = {row.instance_id for row in candidates}
            candidates.extend(
                sorted(
                    (
                        row
                        for row in fallback_rows
                        if row.drift_type == drift_type
                        and row.instance_id not in existing
                        and _can_materialize(row)
                    ),
                    key=lambda row: row.instance_id,
                )
            )
        if len(candidates) < 2:
            raise ValueError(f"development pool has fewer than two {drift_type} rows")
        rng = random.Random(f"{seed}:{drift_type}")
        selected.extend(
            sorted(rng.sample(candidates, 2), key=lambda row: row.instance_id)
        )
    return selected


def _can_materialize(row: DriftInstance) -> bool:
    try:
        materialize(row)
    except Exception:  # noqa: BLE001 - selection excludes any invalid source bundle
        return False
    return True


def build_adaptive_codex_prompt(
    *,
    alias: str,
    clause: RegulationClause,
    program_scope: str,
    tool_command: str,
) -> str:
    """Build one label-free, batch-size-one provider task."""

    visible = json.dumps(
        {
            "alias": alias,
            "program_scope": program_scope,
            "clause": clause.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""\
You are the configuration-3 adaptive COBOL compliance agent. Work on exactly
one opaque case and maintain one evolving D1-D7 hypothesis ledger. This task
has no access to benchmark labels, mutation provenance, scoring data, other
cases, or the orchestration chat.

Use only this bounded command for source evidence:
  {tool_command} {alias} {ADAPTIVE_HUNT} TOOL --arguments 'JSON_OBJECT'
The command returns an observation sequence, bounded observation summary, and
the SHA-256 of that exact summary. You may make at most 16 total tool calls.
Every final evidence-ledger note must cite a successful returned sequence and
hash, name its D1-D7 hypothesis, mark supports/refutes/context, and explain its
bearing. Preserve notes as the investigation evolves. One case may change
hypotheses; do not run seven independent hunts.

The host owns and attaches the real instance identity and trusted clause. Your
prediction therefore contains only the provider-facing fields required by the
output schema. Emit one finding only when its class evidence contract is met,
otherwise emit one explicit abstention. The unchanged host policy guard and
verifier decide whether a finding may be emitted. Do not inspect files except
through the bounded command, parent directories, git data, timestamps,
formatting, comments as edit cues, or identifier style.

Shared adaptive instructions:
{ADAPTIVE_SYSTEM_PROMPT}

Detector-visible case:
{visible}
"""


def _steps(logs: Sequence[ToolLogEntry], alias: str) -> list[ToolCall]:
    relevant = sorted(
        (entry for entry in logs if entry.alias == alias),
        key=lambda entry: entry.sequence,
    )
    if any(entry.hunt != ADAPTIVE_HUNT for entry in relevant):
        raise ValueError("adaptive task contains non-adaptive tool logs")
    sequences = [entry.sequence for entry in relevant]
    if len(sequences) != len(set(sequences)):
        raise ValueError("adaptive tool log contains duplicate sequences")
    if len(relevant) > CONFIG3_AGENT_BUDGET.max_tool_calls:
        raise ValueError("adaptive tool log exceeds the frozen tool budget")
    return [
        ToolCall(
            step=entry.sequence,
            tool=entry.tool,
            arguments=entry.arguments,
            observation_summary=entry.observation_summary,
            observation_truncated=entry.observation_truncated,
            error=entry.error,
            latency_ms=entry.latency_ms,
        )
        for entry in relevant
    ]


def _transcript(steps: Sequence[ToolCall]) -> list[dict[str, Any]]:
    return [
        {
            "step": step.step,
            "tool": step.tool,
            "arguments": step.arguments,
            "observation_summary": step.observation_summary,
            "observation_truncated": step.observation_truncated,
            "error": step.error,
        }
        for step in steps
    ]


def _abstained_outcome(
    *,
    response: AgentResponse,
    question: str,
    steps: list[ToolCall],
    reason: str,
    model_id: str,
    budget: BudgetSpec,
    verification=None,
    budget_exhausted: bool = False,
) -> AdaptiveOutcome:
    trajectory = Trajectory(
        question=question,
        steps=steps,
        model_responses=[response],
        verification=verification,
        finding=None,
        abstained=True,
        abstention_reason=reason,
        budget=budget,
        budget_exhausted=budget_exhausted,
        tokens_used=response.token_count,
        token_usage_recorded=response.token_count_recorded,
        contract_repairs=0,
        final_answer=f"Abstained: {reason}",
        model_id=model_id,
        seed=None,
    )
    hypothesis = (
        response.prediction.drift_type if response.prediction is not None else None
    )
    return AdaptiveOutcome(
        hypothesis=hypothesis,
        finding=None,
        confidence=None,
        verification=verification,
        verification_tier=(verification.tier if verification is not None else None),
        evidence_ledger=list(response.evidence_ledger),
        trajectory=trajectory,
        abstained=True,
        abstention_reason=reason,
    )


def finalize_adaptive_case(
    submitted: SubmittedAdaptiveCase,
    *,
    clause: RegulationClause,
    program_scope: str,
    instance_id: str,
    logs: Sequence[ToolLogEntry],
    tools: ToolLayer,
    entailer: Entailer,
    token_count: int,
    token_count_recorded: bool = True,
    model_id: str = MODEL_ID,
    budget: BudgetSpec = CONFIG3_AGENT_BUDGET,
) -> AdaptiveOutcome:
    """Bind trusted inputs, validate the ledger, then apply guards and verifier."""

    steps = _steps(logs, submitted.alias)
    transcript = _transcript(steps)
    question = build_adaptive_codex_prompt(
        alias=submitted.alias,
        clause=clause,
        program_scope=program_scope,
        tool_command="<frozen-task-tool-command>",
    )
    response = bind_submitted_response(
        submitted.response,
        instance_id=instance_id,
        clause=clause,
        token_count=token_count,
        token_count_recorded=token_count_recorded,
    ).model_copy(update={"evidence_ledger": list(submitted.evidence_ledger)})
    if token_count_recorded and token_count > budget.max_tokens:
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason="token budget exhausted",
            model_id=model_id,
            budget=budget,
            budget_exhausted=True,
        )
    prediction = response.prediction
    ledger_errors = validate_evidence_ledger(
        response.evidence_ledger,
        transcript,
        required_support=(prediction.drift_type if prediction is not None else None),
    )
    if ledger_errors:
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason="adaptive evidence ledger: " + "; ".join(ledger_errors),
            model_id=model_id,
            budget=budget,
        )
    successful = sum(
        step.error is None and bool(step.observation_summary) for step in steps
    )
    if successful < 1:
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason="adaptive evidence minimum not met: no successful observation",
            model_id=model_id,
            budget=budget,
        )
    if response.kind == "abstain":
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason=response.abstention_reason or "model abstained",
            model_id=model_id,
            budget=budget,
        )
    if prediction is None:
        raise RuntimeError("bound adaptive finding lost its prediction")
    hunt = get_hunt(prediction.drift_type)
    guard_errors = hunt.validate_response(response, transcript, clause)
    if guard_errors:
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason="policy evidence guard: " + "; ".join(guard_errors),
            model_id=model_id,
            budget=budget,
        )
    finding = Finding.from_prediction(prediction, claim=response.claim).model_copy(
        update={
            "exec_probe": response.exec_probe,
            "static_claim": response.static_claim,
        }
    )
    try:
        verification = verify(finding, tools, entailer=entailer)
    except Exception as exc:  # noqa: BLE001
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason=(
                "verification unavailable; refusing emission: "
                f"{type(exc).__name__}: {exc}"
            ),
            model_id=model_id,
            budget=budget,
        )
    if not verification.verified:
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason=verification.rejected_reason or "finding was not verified",
            model_id=model_id,
            budget=budget,
            verification=verification,
        )
    trajectory = Trajectory(
        question=question,
        steps=steps,
        model_responses=[response],
        verification=verification,
        finding=prediction,
        abstained=False,
        abstention_reason=None,
        budget=budget,
        budget_exhausted=False,
        tokens_used=token_count,
        token_usage_recorded=token_count_recorded,
        contract_repairs=0,
        final_answer=response.final_answer or verification.evidence,
        model_id=model_id,
        seed=None,
    )
    result_errors = hunt.validate_trajectory(trajectory)
    if result_errors:
        return _abstained_outcome(
            response=response,
            question=question,
            steps=steps,
            reason="policy result guard: " + "; ".join(result_errors),
            model_id=model_id,
            budget=budget,
            verification=verification,
        )
    return AdaptiveOutcome(
        hypothesis=prediction.drift_type,
        finding=prediction,
        confidence=confidence_for_tier(verification.tier),
        verification=verification,
        verification_tier=verification.tier,
        evidence_ledger=list(response.evidence_ledger),
        trajectory=trajectory,
        abstained=False,
        abstention_reason=None,
    )


def bounded_provider_map[ItemT, ResultT](
    items: Sequence[ItemT],
    worker: Callable[[ItemT], ResultT],
    *,
    max_workers: int,
) -> Iterator[tuple[ItemT, ResultT | None, Exception | None]]:
    """Yield provider completions with at most two queued tasks per worker."""

    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    iterator = iter(items)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        active = {}

        def fill() -> None:
            while len(active) < 2 * max_workers:
                try:
                    item = next(iterator)
                except StopIteration:
                    return
                active[executor.submit(worker, item)] = item

        fill()
        while active:
            done, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
            for future in done:
                item = active.pop(future)
                try:
                    yield item, future.result(), None
                except Exception as exc:  # noqa: BLE001
                    yield item, None, exc
            fill()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def ensure_frozen_identity(path: Path, freeze: Config3RunFreeze) -> str:
    """Write the freeze once or reject any attempted identity drift."""

    path = Path(path)
    rendered = freeze.model_dump_json(indent=2)
    if path.exists():
        prior = Config3RunFreeze.model_validate_json(path.read_text(encoding="utf-8"))
        if prior != freeze:
            raise RuntimeError("configuration-3 run freeze differs from existing file")
    else:
        _atomic_write(path, rendered)
    return canonical_sha256(freeze)


def freeze_path_for_transport(
    *, output_dir: Path, transport: Literal["collaboration_subagent", "wsl", "native"]
) -> Path:
    """Keep the repaired collaboration lineage additive to the sealed v1 freeze."""

    name = (
        COLLABORATION_FREEZE_PATH.name
        if transport == "collaboration_subagent"
        else FREEZE_PATH.name
    )
    return Path(output_dir) / name


def _deep_validate_control_artifact(
    *,
    output_dir: Path,
    freeze: Config3RunFreeze,
    system_id: Literal[
        "agent", "plain_llm", "rag_dense", "rag_reranker", "oracle_slice"
    ],
    mode: Literal["smoke", "full"],
    rows: Sequence[DriftInstance],
) -> tuple[dict[str, EvaluationRecord], dict[str, str]]:
    """Recompute requests and replay every control raw batch to canonical equality."""

    from cobol_archaeologist.eval.config3_controls import (
        build_control_contexts,
        build_control_seal,
        replay_agent_batch,
        replay_baseline_batch,
    )

    sources = {row.instance_id: materialize(row) for row in rows}
    contexts = build_control_contexts(system_id, rows=rows, sources=sources)
    seal = build_control_seal(
        freeze=freeze,
        system_id=system_id,
        mode=mode,
        rows=rows,
        sources=sources,
        contexts=contexts,
    )
    seal_path = Path(output_dir) / mode / system_id / "control-seal.json"
    persisted_seal = type(seal).model_validate_json(
        seal_path.read_text(encoding="utf-8")
    )
    if persisted_seal != seal:
        raise RuntimeError(f"{system_id} control seal differs from recomputed identity")
    row_keys = dict(zip(seal.row_order, seal.row_run_keys, strict=True))
    batches = [
        list(rows[index : index + seal.batch_size])
        for index in range(0, len(rows), seal.batch_size)
    ]
    artifact_dir = Path(output_dir) / mode / system_id
    records, markers = _load_record_sidecars(artifact_dir / "records")
    if set(records) != set(seal.row_run_keys) or set(markers) != set(seal.row_run_keys):
        raise RuntimeError(f"{system_id} completed sidecar roster is incomplete")
    canonical_path = artifact_dir / f"{system_id}.jsonl"
    canonical = [
        EvaluationRecord.model_validate_json(line)
        for line in canonical_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ordered_sidecars = [records[row_keys[row.instance_id]] for row in rows]
    if canonical != ordered_sidecars or any(
        record.gold != row
        or record.source_sha256 != sources[row.instance_id].source_sha256
        for record, row in zip(canonical, rows, strict=True)
    ):
        raise RuntimeError(f"{system_id} canonical output differs from frozen sidecars")
    if freeze.transport == "native":
        from cobol_archaeologist.eval.codex_native import native_tool_command

        tool_command = native_tool_command(repository_root=ROOT)
    else:
        support_root = f"{DEFAULT_SUPPORT_BASE}/{freeze.runtime_source_sha256}"
        tool_command = (
            f"{support_root}/.venv/bin/python -m cobol_archaeologist.eval.codex_tool"
        )
    expected_requests: dict[str, str] = {}
    raw_by_run: dict[str, str] = {}
    entailer = default_entailer()
    for batch, batch_key in zip(batches, seal.batch_run_keys, strict=True):
        aliases = [f"drift_{900000 + index:06d}" for index in range(len(batch))]
        alias_rows = dict(zip(aliases, batch, strict=True))
        if system_id == "agent":
            prompt = build_agent_prompt(
                [
                    {
                        "alias": alias,
                        "program_scope": Path(row.provenance.base_program).stem,
                        "clause": row.regulation_clause.model_dump(mode="json"),
                    }
                    for alias, row in alias_rows.items()
                ],
                tool_command=tool_command,
            )
            schema = strict_codex_schema(CodexBatchEnvelope)
            task_sources = {
                alias: sources[row.instance_id] for alias, row in alias_rows.items()
            }
            hunts: Sequence[str] = AGENT_HUNTS
        else:
            prompt = build_baseline_prompt(
                system_id,
                [
                    {
                        "alias": alias,
                        "context": contexts[row.instance_id].model_dump(mode="json"),
                    }
                    for alias, row in alias_rows.items()
                ],
            )
            schema = strict_codex_schema(CodexBaselineEnvelope)
            task_sources = {}
            hunts = ()
        expected_requests[batch_key] = expected_codex_request_sha256(
            prompt=prompt,
            schema=schema,
            sources=task_sources,
            transport=freeze.transport,
            codex_binary=freeze.codex_binary,
            runtime_source_sha256=freeze.runtime_source_sha256,
            chatgpt_account_sha256=freeze.chatgpt_account_sha256,
            authorized_hunts=hunts,
        )
        execution = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=batch_key,
            expected_request_sha256=expected_requests[batch_key],
        )
        if execution is None:
            raise RuntimeError(f"{system_id} raw batch is missing")
        replayed = (
            replay_agent_batch(
                batch=batch,
                execution=execution,
                sources=sources,
                row_keys=row_keys,
                entailer=entailer,
            )
            if system_id == "agent"
            else replay_baseline_batch(
                system_id=system_id,
                batch=batch,
                execution=execution,
                sources=sources,
                contexts=contexts,
                row_keys=row_keys,
                entailer=entailer,
            )
        )
        expected_records = [records[row_keys[row.instance_id]] for row in batch]
        if replayed != expected_records:
            raise RuntimeError(f"{system_id} records differ from raw host replay")
        raw_by_run.update({row_keys[row.instance_id]: batch_key for row in batch})
    _validate_record_raw_chain(
        records=records,
        markers=markers,
        artifact_dir=artifact_dir,
        raw_keys_by_run_key=raw_by_run,
        expected_requests=expected_requests,
    )
    return records, expected_requests


def _deep_validate_adaptive_artifact(
    *,
    output_dir: Path,
    freeze: Config3RunFreeze,
    mode: Literal["smoke", "full"],
    rows: Sequence[DriftInstance],
) -> dict[str, EvaluationRecord]:
    sources = {row.instance_id: materialize(row) for row in rows}
    keys = {
        row.instance_id: config3_run_key(
            freeze=freeze,
            system_id="adaptive_agent",
            run_mode=mode,
            instance_id=row.instance_id,
            source_sha256=sources[row.instance_id].source_sha256,
        )
        for row in rows
    }
    artifact_dir = Path(output_dir) / mode / "adaptive_agent"
    records, markers = _load_record_sidecars(artifact_dir / "records")
    if set(records) != set(keys.values()) or set(markers) != set(keys.values()):
        raise RuntimeError("adaptive completed sidecar roster is incomplete")
    canonical = [
        EvaluationRecord.model_validate_json(line)
        for line in (artifact_dir / "adaptive_agent.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if canonical != [records[keys[row.instance_id]] for row in rows] or any(
        record.gold != row
        or record.source_sha256 != sources[row.instance_id].source_sha256
        for record, row in zip(canonical, rows, strict=True)
    ):
        raise RuntimeError("adaptive canonical output differs from frozen sidecars")
    if freeze.transport == "native":
        from cobol_archaeologist.eval.codex_native import native_tool_command

        tool_command = native_tool_command(repository_root=ROOT)
    else:
        support_root = f"{DEFAULT_SUPPORT_BASE}/{freeze.runtime_source_sha256}"
        tool_command = (
            f"{support_root}/.venv/bin/python -m cobol_archaeologist.eval.codex_tool"
        )
    schema = strict_codex_schema(CodexAdaptiveEnvelope)
    expected: dict[str, str] = {}
    entailer = default_entailer()
    for row in rows:
        key = keys[row.instance_id]
        expected[key] = expected_codex_request_sha256(
            prompt=build_adaptive_codex_prompt(
                alias="drift_900000",
                clause=row.regulation_clause,
                program_scope=Path(row.provenance.base_program).stem,
                tool_command=tool_command,
            ),
            schema=schema,
            sources={"drift_900000": sources[row.instance_id]},
            transport=freeze.transport,
            codex_binary=freeze.codex_binary,
            runtime_source_sha256=freeze.runtime_source_sha256,
            chatgpt_account_sha256=freeze.chatgpt_account_sha256,
            authorized_hunts=(ADAPTIVE_HUNT,),
        )
        execution = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=key,
            expected_request_sha256=expected[key],
        )
        if execution is None:
            raise RuntimeError("adaptive raw execution is missing")
        replayed = _replay_adaptive_record(
            row,
            source=sources[row.instance_id],
            execution=execution,
            key=key,
            entailer=entailer,
        )
        if replayed != records[key]:
            raise RuntimeError("adaptive record differs from raw host replay")
    _validate_record_raw_chain(
        records=records,
        markers=markers,
        artifact_dir=artifact_dir,
        raw_keys_by_run_key={key: key for key in expected},
        expected_requests=expected,
    )
    return records


def _valid_smoke_progress(
    *, output_dir: Path, freeze: Config3RunFreeze, system_id: Config3SystemID
) -> tuple[Config3Progress, str]:
    path = Path(output_dir) / "smoke" / system_id / "progress.json"
    if not path.is_file():
        raise RuntimeError(f"{system_id} has no completed configuration-3 smoke")
    payload = path.read_bytes()
    progress = Config3Progress.model_validate_json(payload)
    if (
        progress.freeze_sha256 != canonical_sha256(freeze)
        or progress.system_id != system_id
        or progress.run_mode != "smoke"
        or progress.status != "VALID"
        or progress.pending_instance_ids
        or progress.interruptions
    ):
        raise RuntimeError(f"{system_id} configuration-3 smoke is not valid")
    if any(
        instance_id not in freeze.source_sha256
        for instance_id in freeze.smoke_instance_ids
    ):
        raise RuntimeError("frozen smoke roster has no pinned source hash")
    expected_keys = {
        config3_run_key(
            freeze=freeze,
            system_id=system_id,
            run_mode="smoke",
            instance_id=instance_id,
            source_sha256=freeze.source_sha256[instance_id],
        )
        for instance_id in freeze.smoke_instance_ids
    }
    if set(progress.completed_run_keys) != expected_keys or len(expected_keys) != 14:
        raise RuntimeError(f"{system_id} smoke does not contain the exact 14 run keys")
    artifact_dir = path.parent
    records, markers = _load_record_sidecars(artifact_dir / "records")
    if set(records) != expected_keys or set(markers) != expected_keys:
        raise RuntimeError(f"{system_id} smoke record sidecars are incomplete")
    rows_by_id = {
        row.instance_id: row
        for row in [
            *_load_split(ROOT / freeze.dev_split_path),
            *_load_split(ROOT / freeze.train_split_path),
        ]
    }
    if (
        hashlib.sha256((ROOT / freeze.dev_split_path).read_bytes()).hexdigest()
        != freeze.dev_split_sha256
        or hashlib.sha256((ROOT / freeze.train_split_path).read_bytes()).hexdigest()
        != freeze.train_split_sha256
    ):
        raise RuntimeError("frozen smoke source split changed")
    smoke_rows = [rows_by_id[instance_id] for instance_id in freeze.smoke_instance_ids]
    if system_id == "adaptive_agent":
        _deep_validate_adaptive_artifact(
            output_dir=output_dir,
            freeze=freeze,
            mode="smoke",
            rows=smoke_rows,
        )
    else:
        _deep_validate_control_artifact(
            output_dir=output_dir,
            freeze=freeze,
            system_id=system_id,
            mode="smoke",
            rows=smoke_rows,
        )
    for record in records.values():
        gold = rows_by_id.get(record.instance_id)
        if (
            gold is None
            or record.gold != gold
            or record.system_id != system_id
            or record.source_sha256 != freeze.source_sha256[record.instance_id]
        ):
            raise RuntimeError(f"{system_id} smoke record identity is invalid")
        marker = markers[record.run_key]
        bundle = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=marker.raw_bundle_key,
            expected_request_sha256=marker.raw_request_sha256,
        )
        if bundle is None or canonical_sha256(bundle) != marker.raw_execution_sha256:
            raise RuntimeError(f"{system_id} smoke raw bundle chain is invalid")
    output_path = artifact_dir / f"{system_id}.jsonl"
    if not output_path.is_file():
        raise RuntimeError(f"{system_id} smoke canonical output is missing")
    output_records = [
        EvaluationRecord.model_validate_json(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if output_records != [
        next(record for record in records.values() if record.instance_id == instance_id)
        for instance_id in freeze.smoke_instance_ids
    ]:
        raise RuntimeError(f"{system_id} smoke canonical output differs from sidecars")
    return progress, hashlib.sha256(payload).hexdigest()


def refresh_smoke_readiness(
    *, output_dir: Path, freeze: Config3RunFreeze
) -> Config3SmokeReadiness | None:
    """Write the immutable global gate only once all six smokes are valid."""

    hashes: dict[str, str] = {}
    for system_id in CONFIG3_SYSTEMS:
        try:
            _, hashes[system_id] = _valid_smoke_progress(
                output_dir=output_dir, freeze=freeze, system_id=system_id
            )
        except RuntimeError:
            return None
    readiness = Config3SmokeReadiness(
        freeze_sha256=canonical_sha256(freeze),
        systems=CONFIG3_SYSTEMS,
        progress_sha256=hashes,
    )
    path = Path(output_dir) / "smoke-readiness.json"
    marker_path = path.with_suffix(".sha256")
    rendered = readiness.model_dump_json(indent=2)
    marker = hashlib.sha256(rendered.encode()).hexdigest() + "\n"
    if path.exists() or marker_path.exists():
        if (
            not path.exists()
            or not marker_path.exists()
            or path.read_text(encoding="utf-8") != rendered
            or marker_path.read_text(encoding="utf-8") != marker
        ):
            raise RuntimeError("refusing to replace configuration-3 smoke readiness")
    else:
        _atomic_write(path, rendered)
        _atomic_write(marker_path, marker)
    return readiness


def require_full_smoke_readiness(
    *,
    output_dir: Path,
    freeze: Config3RunFreeze,
    system_id: Config3SystemID,
) -> Config3SmokeReadiness:
    """Require both the system's smoke and the hash-bound global gate."""

    _valid_smoke_progress(output_dir=output_dir, freeze=freeze, system_id=system_id)
    path = Path(output_dir) / "smoke-readiness.json"
    marker_path = path.with_suffix(".sha256")
    if not path.is_file() or not marker_path.is_file():
        raise RuntimeError("full run requires the global all-six-system smoke gate")
    rendered = path.read_text(encoding="utf-8")
    if (
        marker_path.read_text(encoding="utf-8").strip()
        != hashlib.sha256(rendered.encode()).hexdigest()
    ):
        raise RuntimeError("global smoke-readiness artifact hash mismatch")
    readiness = Config3SmokeReadiness.model_validate_json(rendered)
    current = refresh_smoke_readiness(output_dir=output_dir, freeze=freeze)
    if current is None or readiness != current:
        raise RuntimeError("global all-six-system smoke gate is stale")
    return readiness


def write_temporal_score(
    *, output_dir: Path, freeze: Config3RunFreeze
) -> Config3TemporalScore:
    """Score the pinned temporal pairs and publish an immutable hash-bound gate."""

    artifact_dir = Path(output_dir) / "temporal" / "adaptive_agent"
    progress_path = artifact_dir / "progress.json"
    records_path = artifact_dir / "adaptive_agent.jsonl"
    progress = Config3Progress.model_validate_json(
        progress_path.read_text(encoding="utf-8")
    )
    if (
        progress.status != "VALID"
        or progress.pending_instance_ids
        or progress.interruptions
    ):
        raise RuntimeError("temporal paired scoring requires a valid completed run")
    manifest, rows = load_finalized_t6_rows(
        root=ROOT, manifest_path=ROOT / freeze.t6_v2_path
    )
    materialized = {
        row.instance_id: materialize_finalized_t6_row(
            row, root=ROOT, source_inputs=freeze.t6_source_inputs
        )
        for row in rows
    }
    expected_keys = {
        row.instance_id: config3_run_key(
            freeze=freeze,
            system_id="adaptive_agent",
            run_mode="temporal",
            instance_id=row.instance_id,
            source_sha256=materialized[row.instance_id].source_sha256,
        )
        for row in rows
    }
    if set(progress.completed_run_keys) != set(expected_keys.values()):
        raise RuntimeError("temporal progress differs from exact 40 frozen run keys")
    records = [
        EvaluationRecord.model_validate_json(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records_by_id = {record.instance_id: record for record in records}
    rows_by_id = {row.instance_id: row for row in rows}
    sidecars, markers = _load_record_sidecars(artifact_dir / "records")
    if (
        tuple(record.instance_id for record in records) != manifest.instance_order
        or len(records_by_id) != 40
        or any(records_by_id[item].gold != rows_by_id[item] for item in rows_by_id)
        or set(sidecars) != set(expected_keys.values())
        or set(markers) != set(expected_keys.values())
        or records
        != [
            sidecars[expected_keys[instance_id]]
            for instance_id in manifest.instance_order
        ]
    ):
        raise RuntimeError("temporal records differ from the finalized T6 roster")
    if freeze.transport == "native":
        from cobol_archaeologist.eval.codex_native import native_tool_command

        tool_command = native_tool_command(repository_root=ROOT)
    else:
        support_root = f"{DEFAULT_SUPPORT_BASE}/{freeze.runtime_source_sha256}"
        tool_command = (
            f"{support_root}/.venv/bin/python -m cobol_archaeologist.eval.codex_tool"
        )
    schema = strict_codex_schema(CodexAdaptiveEnvelope)
    expected_requests: dict[str, str] = {}
    for row in rows:
        key = expected_keys[row.instance_id]
        prompt = build_adaptive_codex_prompt(
            alias="drift_900000",
            clause=row.regulation_clause,
            program_scope=Path(row.provenance.base_program).stem,
            tool_command=tool_command,
        )
        expected_requests[key] = expected_codex_request_sha256(
            prompt=prompt,
            schema=schema,
            sources={"drift_900000": materialized[row.instance_id]},
            transport=freeze.transport,
            codex_binary=freeze.codex_binary,
            runtime_source_sha256=freeze.runtime_source_sha256,
            chatgpt_account_sha256=freeze.chatgpt_account_sha256,
            authorized_hunts=(ADAPTIVE_HUNT,),
        )
    _validate_record_raw_chain(
        records=sidecars,
        markers=markers,
        artifact_dir=artifact_dir,
        raw_keys_by_run_key={key: key for key in expected_keys.values()},
        expected_requests=expected_requests,
    )
    entailer = default_entailer()
    for row in rows:
        key = expected_keys[row.instance_id]
        execution = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=key,
            expected_request_sha256=expected_requests[key],
        )
        assert execution is not None
        envelope = CodexAdaptiveEnvelope.model_validate_json(execution.final_message)
        submitted = envelope.results[0]
        if submitted.alias != "drift_900000":
            raise RuntimeError("temporal replay returned the wrong opaque alias")
        with tempfile.TemporaryDirectory(prefix="m4-config3-temporal-replay-") as temp:
            tools = _tool_layer(materialized[row.instance_id], Path(temp), None)
            outcome = finalize_adaptive_case(
                submitted,
                clause=row.regulation_clause,
                program_scope=Path(row.provenance.base_program).stem,
                instance_id=row.instance_id,
                logs=execution.tool_logs,
                tools=tools,
                entailer=entailer,
                token_count=(
                    execution.parsed.usage.total_tokens
                    if execution.parsed.usage is not None
                    else 0
                ),
                token_count_recorded=execution.parsed.usage is not None,
            )
        replayed = _record_adaptive_outcome(
            row,
            outcome,
            source_sha256=materialized[row.instance_id].source_sha256,
            key=key,
        )
        if replayed != records_by_id[row.instance_id]:
            raise RuntimeError("temporal canonical record differs from raw replay")

    def correct(record: EvaluationRecord) -> bool:
        return bool(
            not record.infrastructure_error
            and not record.abstained
            and record.prediction is not None
            and (record.prediction.drift_type != "D7_conformant")
            == (record.gold.drift_type != "D7_conformant")
        )

    pairs = tuple(
        TemporalPairScore(
            pair_id=pair_id,
            instance_ids=manifest.pair_members[pair_id],
            authority_target=manifest.authority_targets[pair_id],
            side_correct=tuple(
                correct(records_by_id[item]) for item in manifest.pair_members[pair_id]
            ),
            pair_correct=all(
                correct(records_by_id[item]) for item in manifest.pair_members[pair_id]
            ),
        )
        for pair_id in manifest.pair_order
    )
    paired_correct = sum(pair.pair_correct for pair in pairs)
    score = Config3TemporalScore(
        freeze_sha256=canonical_sha256(freeze),
        finalized_t6_sha256=freeze.t6_v2_sha256,
        records_sha256=hashlib.sha256(records_path.read_bytes()).hexdigest(),
        pair_order=manifest.pair_order,
        pairs=pairs,
        paired_correct=paired_correct,
        paired_accuracy=paired_correct / 20,
    )
    path = artifact_dir / "paired-score.json"
    marker_path = path.with_suffix(".sha256")
    rendered = score.model_dump_json(indent=2)
    marker = hashlib.sha256(rendered.encode()).hexdigest() + "\n"
    if path.exists() or marker_path.exists():
        if (
            not path.exists()
            or not marker_path.exists()
            or path.read_text(encoding="utf-8") != rendered
            or marker_path.read_text(encoding="utf-8") != marker
        ):
            raise RuntimeError("refusing to replace temporal paired score")
    else:
        _atomic_write(path, rendered)
        _atomic_write(marker_path, marker)
    return score


def require_temporal_score(
    *, output_dir: Path, freeze: Config3RunFreeze
) -> Config3TemporalScore:
    path = Path(output_dir) / "temporal" / "adaptive_agent" / "paired-score.json"
    marker_path = path.with_suffix(".sha256")
    if not path.is_file() or not marker_path.is_file():
        raise RuntimeError("configuration-3 decision requires paired temporal score")
    rendered = path.read_text(encoding="utf-8")
    if (
        marker_path.read_text(encoding="utf-8").strip()
        != hashlib.sha256(rendered.encode()).hexdigest()
    ):
        raise RuntimeError("temporal paired score hash mismatch")
    score = Config3TemporalScore.model_validate_json(rendered)
    current = write_temporal_score(output_dir=output_dir, freeze=freeze)
    if score != current:
        raise RuntimeError("temporal paired score is stale")
    return score


def write_config3_quality_metrics(
    *, output_dir: Path, freeze: Config3RunFreeze
) -> Config3QualityMetrics:
    """Derive and pin every predeclared T8.1 utility and evidence gate."""

    if runtime_source_sha256(ROOT) != freeze.runtime_source_sha256:
        raise RuntimeError("quality scoring runtime differs from the frozen snapshot")
    identity_paths = {
        "evidence_policy": ROOT / "src" / "cobol_archaeologist" / "agent" / "policy.py",
        "verifier": ROOT / "src" / "cobol_archaeologist" / "model" / "verify.py",
    }
    for name, path in identity_paths.items():
        if (
            freeze.identity_hashes.get(name)
            != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise RuntimeError(f"frozen {name} identity changed before quality scoring")
    adaptive_path = (
        Path(output_dir) / "full" / "adaptive_agent" / "adaptive_agent.jsonl"
    )
    reranker_path = Path(output_dir) / "full" / "rag_reranker" / "rag_reranker.jsonl"
    frozen_rows = _load_split(ROOT / freeze.test_split_path)
    frozen_by_id = {row.instance_id: row for row in frozen_rows}

    def load_records(path: Path, system_id: Config3SystemID) -> list[EvaluationRecord]:
        records = [
            EvaluationRecord.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if (
            tuple(record.instance_id for record in records) != freeze.test_order
            or len({record.instance_id for record in records}) != len(freeze.test_order)
            or any(record.system_id != system_id for record in records)
            or any(record.infrastructure_error for record in records)
            or any(
                record.gold != frozen_by_id.get(record.instance_id)
                or record.source_sha256 != freeze.source_sha256.get(record.instance_id)
                for record in records
            )
        ):
            raise RuntimeError(f"{system_id} full artifact is not valid for scoring")
        sidecars, markers = _load_record_sidecars(path.parent / "records")
        expected_keys = {
            config3_run_key(
                freeze=freeze,
                system_id=system_id,
                run_mode="full",
                instance_id=record.instance_id,
                source_sha256=record.source_sha256,
            )
            for record in records
        }
        try:
            ordered_sidecars = [
                next(
                    record
                    for record in sidecars.values()
                    if record.instance_id == instance_id
                )
                for instance_id in freeze.test_order
            ]
        except StopIteration as exc:
            raise RuntimeError(f"{system_id} sidecar roster is incomplete") from exc
        if (
            set(sidecars) != expected_keys
            or set(markers) != expected_keys
            or records != ordered_sidecars
        ):
            raise RuntimeError(f"{system_id} canonical output differs from sidecars")
        for record in records:
            marker = markers[record.run_key]
            bundle = load_execution_bundle(
                artifact_dir=path.parent,
                key=marker.raw_bundle_key,
                expected_request_sha256=marker.raw_request_sha256,
            )
            if (
                bundle is None
                or canonical_sha256(bundle) != marker.raw_execution_sha256
            ):
                raise RuntimeError(f"{system_id} raw execution chain is invalid")
        return records

    adaptive = load_records(adaptive_path, "adaptive_agent")
    reranker = load_records(reranker_path, "rag_reranker")
    if any(
        left.gold != right.gold or left.source_sha256 != right.source_sha256
        for left, right in zip(adaptive, reranker, strict=True)
    ):
        raise RuntimeError("adaptive/rag_reranker paired inputs differ")
    sources = {row.instance_id: materialize(row) for row in frozen_rows}
    if freeze.transport == "native":
        from cobol_archaeologist.eval.codex_native import native_tool_command

        tool_command = native_tool_command(repository_root=ROOT)
    else:
        support_root = f"{DEFAULT_SUPPORT_BASE}/{freeze.runtime_source_sha256}"
        tool_command = (
            f"{support_root}/.venv/bin/python -m cobol_archaeologist.eval.codex_tool"
        )
    adaptive_schema = strict_codex_schema(CodexAdaptiveEnvelope)
    adaptive_expected = {
        record.run_key: expected_codex_request_sha256(
            prompt=build_adaptive_codex_prompt(
                alias="drift_900000",
                clause=record.gold.regulation_clause,
                program_scope=Path(record.gold.provenance.base_program).stem,
                tool_command=tool_command,
            ),
            schema=adaptive_schema,
            sources={"drift_900000": sources[record.instance_id]},
            transport=freeze.transport,
            codex_binary=freeze.codex_binary,
            runtime_source_sha256=freeze.runtime_source_sha256,
            chatgpt_account_sha256=freeze.chatgpt_account_sha256,
            authorized_hunts=(ADAPTIVE_HUNT,),
        )
        for record in adaptive
    }
    adaptive_sidecars, adaptive_markers = _load_record_sidecars(
        adaptive_path.parent / "records"
    )
    _validate_record_raw_chain(
        records=adaptive_sidecars,
        markers=adaptive_markers,
        artifact_dir=adaptive_path.parent,
        raw_keys_by_run_key={key: key for key in adaptive_expected},
        expected_requests=adaptive_expected,
    )
    replay_entailer = default_entailer()
    for record in adaptive:
        execution = load_execution_bundle(
            artifact_dir=adaptive_path.parent,
            key=record.run_key,
            expected_request_sha256=adaptive_expected[record.run_key],
        )
        assert execution is not None
        replayed = _replay_adaptive_record(
            record.gold,
            source=sources[record.instance_id],
            execution=execution,
            key=record.run_key,
            entailer=replay_entailer,
        )
        if replayed != record:
            raise RuntimeError("adaptive full record differs from raw replay")
    from cobol_archaeologist.eval.config3_controls import (
        build_control_contexts,
        control_batch_key,
        replay_baseline_batch,
    )

    contexts = build_control_contexts("rag_reranker", rows=frozen_rows, sources=sources)
    batch_size = batch_size_for("rag_reranker")
    reranker_expected: dict[str, str] = {}
    reranker_raw_by_run: dict[str, str] = {}
    for start in range(0, len(frozen_rows), batch_size):
        batch = frozen_rows[start : start + batch_size]
        aliases = [f"drift_{900000 + index:06d}" for index in range(len(batch))]
        alias_rows = dict(zip(aliases, batch, strict=True))
        prompt = build_baseline_prompt(
            "rag_reranker",
            [
                {
                    "alias": alias,
                    "context": contexts[row.instance_id].model_dump(mode="json"),
                }
                for alias, row in alias_rows.items()
            ],
        )
        row_run_keys = [
            next(
                record.run_key
                for record in reranker
                if record.instance_id == row.instance_id
            )
            for row in batch
        ]
        batch_key = control_batch_key(
            freeze=freeze,
            system_id="rag_reranker",
            mode="full",
            row_run_keys=row_run_keys,
        )
        reranker_expected[batch_key] = expected_codex_request_sha256(
            prompt=prompt,
            schema=strict_codex_schema(CodexBaselineEnvelope),
            sources={},
            transport=freeze.transport,
            codex_binary=freeze.codex_binary,
            runtime_source_sha256=freeze.runtime_source_sha256,
            chatgpt_account_sha256=freeze.chatgpt_account_sha256,
            authorized_hunts=(),
        )
        reranker_raw_by_run.update({key: batch_key for key in row_run_keys})
        execution = load_execution_bundle(
            artifact_dir=reranker_path.parent,
            key=batch_key,
            expected_request_sha256=reranker_expected[batch_key],
        )
        if execution is None:
            raise RuntimeError("reranker raw batch is missing")
        replayed = replay_baseline_batch(
            system_id="rag_reranker",
            batch=batch,
            execution=execution,
            sources=sources,
            contexts=contexts,
            row_keys={record.instance_id: record.run_key for record in reranker},
            entailer=replay_entailer,
        )
        expected_batch = [
            next(record for record in reranker if record.instance_id == row.instance_id)
            for row in batch
        ]
        if replayed != expected_batch:
            raise RuntimeError("reranker full records differ from raw replay")
    reranker_sidecars, reranker_markers = _load_record_sidecars(
        reranker_path.parent / "records"
    )
    _validate_record_raw_chain(
        records=reranker_sidecars,
        markers=reranker_markers,
        artifact_dir=reranker_path.parent,
        raw_keys_by_run_key=reranker_raw_by_run,
        expected_requests=reranker_expected,
    )
    unverified = sum(
        not record.abstained
        and (
            record.prediction is None
            or record.verification is None
            or not record.verification.verified
        )
        for record in adaptive
    )
    if unverified:
        raise RuntimeError("adaptive full artifact contains unverified emissions")
    overall = detection(adaptive)
    balanced = _balanced_accuracy_structured(adaptive)
    comparison = paired_f1_comparison(
        adaptive,
        reranker,
        locus="interprocedural",
        bootstrap_resamples=freeze.decision_bootstrap_resamples,
        randomization_samples=freeze.decision_randomization_samples,
        seed=freeze.decision_statistics_seed,
    )
    temporal = require_temporal_score(output_dir=output_dir, freeze=freeze)
    gates = {
        "t1_f1": overall["f1"] >= 0.70,
        "balanced_accuracy": balanced >= 0.65,
        "answer_rate": overall["answer_rate"] >= 0.60,
        "answered_accuracy": overall["answered_accuracy"] >= 0.80,
        "interprocedural_advantage": (
            comparison["delta_f1"] >= 0.10
            and comparison["bootstrap_95_ci"][0] > 0
            and comparison["paired_randomization_p"] < 0.05
        ),
        "temporal_paired_accuracy": (
            len(temporal.pairs) >= 20 and temporal.paired_accuracy >= 0.70
        ),
        "verified_evidence": True,
    }
    temporal_path = (
        Path(output_dir) / "temporal" / "adaptive_agent" / "paired-score.json"
    )
    metrics = Config3QualityMetrics(
        freeze_sha256=canonical_sha256(freeze),
        adaptive_records_sha256=hashlib.sha256(adaptive_path.read_bytes()).hexdigest(),
        rag_reranker_records_sha256=hashlib.sha256(
            reranker_path.read_bytes()
        ).hexdigest(),
        temporal_score_sha256=hashlib.sha256(temporal_path.read_bytes()).hexdigest(),
        evidence_policy_sha256=freeze.identity_hashes["evidence_policy"],
        verifier_sha256=freeze.identity_hashes["verifier"],
        bootstrap_resamples=freeze.decision_bootstrap_resamples,
        randomization_samples=freeze.decision_randomization_samples,
        statistics_seed=freeze.decision_statistics_seed,
        t1_f1=overall["f1"],
        balanced_accuracy=balanced,
        answer_rate=overall["answer_rate"],
        answered_accuracy=overall["answered_accuracy"],
        interprocedural=Config3InterproceduralComparison(
            paired_rows=comparison["paired_rows"],
            adaptive_f1=comparison["left_f1"],
            rag_reranker_f1=comparison["right_f1"],
            delta_f1=comparison["delta_f1"],
            bootstrap_95_ci=tuple(comparison["bootstrap_95_ci"]),
            paired_randomization_p=comparison["paired_randomization_p"],
        ),
        temporal_pair_count=len(temporal.pairs),
        temporal_paired_accuracy=temporal.paired_accuracy,
        unverified_emissions=0,
        evidence_threshold_relaxed=False,
        gates=gates,
        all_gates_pass=all(gates.values()),
    )
    path = Path(output_dir) / "configuration-3-quality.json"
    marker_path = path.with_suffix(".sha256")
    rendered = metrics.model_dump_json(indent=2)
    marker = hashlib.sha256(rendered.encode()).hexdigest() + "\n"
    if path.exists() or marker_path.exists():
        if (
            not path.exists()
            or not marker_path.exists()
            or path.read_text(encoding="utf-8") != rendered
            or marker_path.read_text(encoding="utf-8") != marker
        ):
            raise RuntimeError("refusing to replace configuration-3 quality metrics")
    else:
        _atomic_write(path, rendered)
        _atomic_write(marker_path, marker)
    return metrics


def write_configuration3_decision(
    *, output_dir: Path, freeze: Config3RunFreeze
) -> tuple[Configuration3DecisionArtifact, str]:
    """Derive the exact migration decision from immutable completed evidence."""

    progress_hashes: dict[str, str] = {}
    evaluable = True
    for system_id in CONFIG3_SYSTEMS:
        path = Path(output_dir) / "full" / system_id / "progress.json"
        try:
            payload = path.read_bytes()
            progress = Config3Progress.model_validate_json(payload)
            expected_keys = {
                config3_run_key(
                    freeze=freeze,
                    system_id=system_id,
                    run_mode="full",
                    instance_id=instance_id,
                    source_sha256=freeze.source_sha256[instance_id],
                )
                for instance_id in freeze.test_order
            }
            if (
                progress.freeze_sha256 != canonical_sha256(freeze)
                or progress.system_id != system_id
                or progress.run_mode != "full"
                or progress.status != "VALID"
                or set(progress.completed_run_keys) != expected_keys
                or progress.pending_instance_ids
                or progress.interruptions
            ):
                evaluable = False
            artifact_dir = path.parent
            records, markers = _load_record_sidecars(artifact_dir / "records")
            if set(records) != expected_keys or set(markers) != expected_keys:
                evaluable = False
            gold_by_id = {
                row.instance_id: row
                for row in _load_split(ROOT / freeze.test_split_path)
            }
            if (
                hashlib.sha256((ROOT / freeze.test_split_path).read_bytes()).hexdigest()
                != freeze.test_split_sha256
            ):
                evaluable = False
            for record in records.values():
                marker = markers[record.run_key]
                bundle = load_execution_bundle(
                    artifact_dir=artifact_dir,
                    key=marker.raw_bundle_key,
                    expected_request_sha256=marker.raw_request_sha256,
                )
                if (
                    gold_by_id.get(record.instance_id) != record.gold
                    or record.system_id != system_id
                    or record.source_sha256
                    != freeze.source_sha256.get(record.instance_id)
                    or bundle is None
                    or canonical_sha256(bundle) != marker.raw_execution_sha256
                ):
                    evaluable = False
            canonical_path = artifact_dir / f"{system_id}.jsonl"
            canonical_records = [
                EvaluationRecord.model_validate_json(line)
                for line in canonical_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if tuple(
                record.instance_id for record in canonical_records
            ) != freeze.test_order or canonical_records != [
                next(
                    record
                    for record in records.values()
                    if record.instance_id == instance_id
                )
                for instance_id in freeze.test_order
            ]:
                evaluable = False
            full_rows = [gold_by_id[instance_id] for instance_id in freeze.test_order]
            if system_id == "adaptive_agent":
                _deep_validate_adaptive_artifact(
                    output_dir=output_dir,
                    freeze=freeze,
                    mode="full",
                    rows=full_rows,
                )
            else:
                _deep_validate_control_artifact(
                    output_dir=output_dir,
                    freeze=freeze,
                    system_id=system_id,
                    mode="full",
                    rows=full_rows,
                )
            progress_hashes[system_id] = hashlib.sha256(payload).hexdigest()
        except (KeyError, OSError, RuntimeError, StopIteration, ValueError):
            evaluable = False
    score_hash: str | None = None
    quality: Config3QualityMetrics | None = None
    quality_hash: str | None = None
    try:
        require_temporal_score(output_dir=output_dir, freeze=freeze)
        score_path = (
            Path(output_dir) / "temporal" / "adaptive_agent" / "paired-score.json"
        )
        score_hash = hashlib.sha256(score_path.read_bytes()).hexdigest()
        quality = write_config3_quality_metrics(output_dir=output_dir, freeze=freeze)
        quality_path = Path(output_dir) / "configuration-3-quality.json"
        quality_hash = hashlib.sha256(quality_path.read_bytes()).hexdigest()
    except (OSError, RuntimeError, ValueError):
        evaluable = False
    status: Literal["GO", "NO_GO", "NOT_EVALUABLE"]
    if not evaluable or quality is None:
        status = "NOT_EVALUABLE"
    elif quality.all_gates_pass:
        status = "GO"
    else:
        status = "NO_GO"
    inputs = Configuration3DecisionInputs(
        freeze_sha256=canonical_sha256(freeze),
        full_progress_sha256=progress_hashes,
        temporal_score_sha256=score_hash,
        quality_metrics_sha256=quality_hash,
        derived_status=status,
    )
    decision = Configuration3DecisionArtifact(status=status)
    root = Path(output_dir)
    inputs_path = root / "configuration-3-decision.inputs.json"
    decision_path = root / "configuration-3-decision.json"
    for path, rendered in (
        (inputs_path, inputs.model_dump_json(indent=2)),
        (decision_path, decision.model_dump_json(indent=2)),
    ):
        marker_path = path.with_suffix(".sha256")
        marker = hashlib.sha256(rendered.encode()).hexdigest() + "\n"
        if path.exists() or marker_path.exists():
            if (
                not path.exists()
                or not marker_path.exists()
                or path.read_text(encoding="utf-8") != rendered
                or marker_path.read_text(encoding="utf-8") != marker
            ):
                raise RuntimeError(f"refusing to replace immutable {path.name}")
        else:
            _atomic_write(path, rendered)
            _atomic_write(marker_path, marker)
    return decision, hashlib.sha256(decision_path.read_bytes()).hexdigest()


def validate_configuration3_decision(
    *,
    output_dir: Path,
    freeze: Config3RunFreeze,
    expected_sha256: str | None = None,
) -> Configuration3DecisionArtifact:
    """Validate the canonical decision and its separately pinned derivation inputs."""

    root = Path(output_dir)
    decision_path = root / "configuration-3-decision.json"
    inputs_path = root / "configuration-3-decision.inputs.json"
    for path in (decision_path, inputs_path):
        marker_path = path.with_suffix(".sha256")
        if not path.is_file() or not marker_path.is_file():
            raise RuntimeError(f"configuration-3 artifact is missing: {path.name}")
        if (
            marker_path.read_text(encoding="utf-8").strip()
            != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise RuntimeError(f"configuration-3 artifact hash mismatch: {path.name}")
    actual_sha256 = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise RuntimeError("configuration-3 decision differs from its expected pin")
    decision = Configuration3DecisionArtifact.model_validate_json(
        decision_path.read_text(encoding="utf-8")
    )
    inputs = Configuration3DecisionInputs.model_validate_json(
        inputs_path.read_text(encoding="utf-8")
    )
    quality: Config3QualityMetrics | None = None
    if inputs.quality_metrics_sha256 is not None:
        quality_path = root / "configuration-3-quality.json"
        quality_marker = quality_path.with_suffix(".sha256")
        if (
            not quality_path.is_file()
            or not quality_marker.is_file()
            or hashlib.sha256(quality_path.read_bytes()).hexdigest()
            != inputs.quality_metrics_sha256
            or quality_marker.read_text(encoding="utf-8").strip()
            != inputs.quality_metrics_sha256
        ):
            raise RuntimeError("configuration-3 quality metrics hash mismatch")
        quality = Config3QualityMetrics.model_validate_json(
            quality_path.read_text(encoding="utf-8")
        )
    expected_status = (
        "GO"
        if quality is not None and quality.all_gates_pass
        else "NO_GO"
        if quality is not None
        else "NOT_EVALUABLE"
    )
    if (
        inputs.freeze_sha256 != canonical_sha256(freeze)
        or decision.status != inputs.derived_status
        or decision.status != expected_status
        or (quality is not None and quality.freeze_sha256 != canonical_sha256(freeze))
    ):
        raise RuntimeError("configuration-3 decision differs from pinned inputs")
    return decision


def load_revalidate_configuration3_decision(
    *, output_dir: Path, freeze: Config3RunFreeze
) -> tuple[Configuration3DecisionArtifact, str]:
    """Re-derive then validate the sole canonical migration-facing decision."""

    _, decision_sha256 = write_configuration3_decision(
        output_dir=output_dir, freeze=freeze
    )
    decision = validate_configuration3_decision(
        output_dir=output_dir,
        freeze=freeze,
        expected_sha256=decision_sha256,
    )
    return decision, decision_sha256


def load_verified_config3_detector_records(
    *, output_dir: Path, freeze: Config3RunFreeze
) -> tuple[list[EvaluationRecord], str]:
    """Return adaptive detector rows only after the complete quality chain validates."""

    write_config3_quality_metrics(output_dir=output_dir, freeze=freeze)
    path = Path(output_dir) / "full" / "adaptive_agent" / "adaptive_agent.jsonl"
    records = [
        EvaluationRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records, hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle_dir(artifact_dir: Path, key: str) -> Path:
    return artifact_dir / "raw" / key


def expected_codex_request_sha256(
    *,
    prompt: str,
    schema: Mapping[str, Any],
    sources: Mapping[str, MaterializedSource],
    transport: Literal["wsl", "native"],
    codex_binary: str,
    runtime_source_sha256: str,
    chatgpt_account_sha256: str,
    authorized_hunts: Sequence[str],
) -> str:
    """Build the stable request identity before staging a random task root."""

    placeholder = "<TASK_ROOT>"
    if transport == "native":
        from cobol_archaeologist.eval.codex_native import native_codex_exec_arguments

        arguments = native_codex_exec_arguments(
            codex_binary=codex_binary,
            task_root=Path(placeholder),
            model_id=MODEL_ID,
            reasoning_effort=REASONING_EFFORT,
            allow_tool_bridge=bool(sources),
        )
    else:
        arguments = codex_exec_arguments(
            codex_binary=codex_binary,
            task_root=placeholder,
            model_id=MODEL_ID,
            reasoning_effort=REASONING_EFFORT,
            allow_tool_bridge=bool(sources),
        )
    return codex_request_sha256(
        prompt=prompt,
        schema=schema,
        sources=sources,
        model_id=MODEL_ID,
        reasoning_effort=REASONING_EFFORT,
        cli_arguments=arguments,
        runtime_source_sha256=runtime_source_sha256,
        transport=transport,
        authentication_identity_sha256=chatgpt_account_sha256,
        authorized_hunts=authorized_hunts,
        task_root=placeholder,
    )


ProviderTaskExecution = (
    CodexTaskExecution
    | CollaborationSubagentExecution
    | CollaborationSubagentExecutionV2
)


def load_staged_collaboration_capture_logs(
    *,
    staged: StagedCollaborationTask,
    staging_base: Path,
) -> tuple[ToolLogEntry, ...]:
    """Load exact host-owned logs for a v2 capture submission handoff."""

    logs = load_staged_tool_logs(
        staging_base=staging_base,
        run_key=staged.run_key,
        expected_staging_sha256=staged.staging_sha256,
    )
    for log in logs:
        if tool_log_entry_sha256(log) != collaboration_tool_log_sha256(log):
            raise RuntimeError("staging and capture tool-log hashes disagree")
    return logs


def validate_staged_collaboration_execution(
    execution: ProviderTaskExecution,
    *,
    staged: StagedCollaborationTask,
    staging_base: Path,
) -> None:
    """Require a sealed v2 execution to consume the exact staged host chain."""

    if not isinstance(execution, CollaborationSubagentExecutionV2):
        raise TypeError("staged collaboration requests require a v2 capture bundle")
    logs = load_staged_collaboration_capture_logs(
        staged=staged,
        staging_base=staging_base,
    )
    if tuple(execution.tool_logs) != logs:
        raise ValueError("sealed collaboration tool logs differ from staged host logs")
    observed = [
        event["payload"]
        for event in execution.parsed.events
        if event.get("type") == "tool.completed"
    ]
    expected = [
        collaboration_tool_receipt_payload(
            task_id=execution.task_id,
            request_sha256=execution.request_sha256,
            log=log,
        )
        for log in logs
    ]
    if observed != expected:
        raise ValueError("sealed collaboration tool receipts differ from staged logs")


def _validate_execution_integrity(execution: ProviderTaskExecution) -> None:
    event_hash = hashlib.sha256(
        json.dumps(
            execution.parsed.events,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    log_hash = hashlib.sha256(
        json.dumps(
            [entry.model_dump(mode="json") for entry in execution.tool_logs],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if (
        event_hash != execution.event_stream_sha256
        or log_hash != execution.tool_logs_sha256
    ):
        raise ValueError("Codex execution event/tool evidence hash mismatch")


def persist_execution_bundle(
    execution: CodexTaskExecution,
    *,
    artifact_dir: Path,
    key: str,
    expected_request_sha256: str | None = None,
) -> None:
    """Persist raw provider evidence under its immutable key; marker last."""

    _validate_execution_integrity(execution)
    if (
        expected_request_sha256 is not None
        and execution.request_sha256 != expected_request_sha256
    ):
        raise ValueError(f"Codex execution request identity mismatch for {key}")
    target = _bundle_dir(artifact_dir, key)
    execution_path = target / "execution.json"
    marker_path = target / "complete"
    marker = ExecutionBundleMarker(
        key=key,
        execution_sha256=canonical_sha256(execution),
        request_sha256=execution.request_sha256,
        event_stream_sha256=execution.event_stream_sha256,
        tool_logs_sha256=execution.tool_logs_sha256,
    )
    if execution_path.exists() or marker_path.exists():
        prior = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=key,
            expected_request_sha256=expected_request_sha256,
        )
        if prior != execution:
            raise RuntimeError(f"refusing to overwrite immutable raw bundle {key}")
        return
    target.mkdir(parents=True, exist_ok=False)
    _atomic_write(execution_path, execution.model_dump_json(indent=2))
    _atomic_write(marker_path, marker.model_dump_json(indent=2))


def load_execution_bundle(
    *,
    artifact_dir: Path,
    key: str,
    expected_request_sha256: str | None = None,
) -> ProviderTaskExecution | None:
    target = _bundle_dir(artifact_dir, key)
    execution_path = target / "execution.json"
    marker = target / "complete"
    if not execution_path.exists() or not marker.exists():
        return None
    raw_payload = json.loads(execution_path.read_text(encoding="utf-8"))
    if raw_payload.get("transport") == "collaboration_subagent":
        return load_collaboration_bundle(
            artifact_dir=artifact_dir,
            key=key,
            expected_request_sha256=expected_request_sha256,
        )
    execution = CodexTaskExecution.model_validate_json(json.dumps(raw_payload))
    _validate_execution_integrity(execution)
    if (
        expected_request_sha256 is not None
        and execution.request_sha256 != expected_request_sha256
    ):
        raise ValueError(f"raw execution request identity mismatch for {key}")
    try:
        completed = ExecutionBundleMarker.model_validate_json(
            marker.read_text(encoding="utf-8")
        )
    except ValueError as exc:
        raise ValueError(f"raw execution bundle hash mismatch for {key}") from exc
    expected = ExecutionBundleMarker(
        key=key,
        execution_sha256=canonical_sha256(execution),
        request_sha256=execution.request_sha256,
        event_stream_sha256=execution.event_stream_sha256,
        tool_logs_sha256=execution.tool_logs_sha256,
    )
    if completed != expected:
        raise ValueError(f"raw execution bundle hash mismatch for {key}")
    return execution


def _record_adaptive_outcome(
    row: DriftInstance,
    outcome: AdaptiveOutcome,
    *,
    source_sha256: str,
    key: str,
) -> EvaluationRecord:
    return EvaluationRecord(
        instance_id=row.instance_id,
        gold=row,
        prediction=outcome.finding,
        confidence=outcome.confidence,
        verification=outcome.verification,
        trajectory=outcome.trajectory,
        abstained=outcome.abstained,
        abstention_reason=outcome.abstention_reason,
        system_id="adaptive_agent",
        source_sha256=source_sha256,
        run_key=key,
    )


def _replay_adaptive_record(
    row: DriftInstance,
    *,
    source: MaterializedSource,
    execution: ProviderTaskExecution,
    key: str,
    entailer: Entailer,
) -> EvaluationRecord:
    envelope = CodexAdaptiveEnvelope.model_validate_json(execution.final_message)
    submitted = envelope.results[0]
    if submitted.alias != "drift_900000":
        raise ValueError("adaptive replay returned the wrong opaque alias")
    with tempfile.TemporaryDirectory(prefix="m4-config3-adaptive-replay-") as temp:
        tools = _tool_layer(source, Path(temp), None)
        outcome = finalize_adaptive_case(
            submitted,
            clause=row.regulation_clause,
            program_scope=Path(row.provenance.base_program).stem,
            instance_id=row.instance_id,
            logs=execution.tool_logs,
            tools=tools,
            entailer=entailer,
            token_count=(
                execution.parsed.usage.total_tokens
                if execution.parsed.usage is not None
                else 0
            ),
            token_count_recorded=execution.parsed.usage is not None,
        )
    return _record_adaptive_outcome(
        row,
        outcome,
        source_sha256=source.source_sha256,
        key=key,
    )


def _load_record_sidecars(
    directory: Path,
) -> tuple[dict[str, EvaluationRecord], dict[str, RecordSidecarMarker]]:
    records: dict[str, EvaluationRecord] = {}
    markers: dict[str, RecordSidecarMarker] = {}
    if not directory.exists():
        return records, markers
    json_paths = sorted(directory.glob("*.json"))
    marker_paths = sorted(directory.glob("*.sha256"))
    if {path.stem for path in json_paths} != {path.stem for path in marker_paths}:
        raise ValueError("record sidecars and content-hash markers differ")
    for path in json_paths:
        marker = RecordSidecarMarker.model_validate_json(
            (directory / f"{path.stem}.sha256").read_text(encoding="utf-8")
        )
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if marker.record_sha256 != actual_hash or marker.run_key != path.stem:
            raise ValueError(f"record sidecar hash mismatch: {path.name}")
        record = EvaluationRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.run_key != path.stem:
            raise ValueError("record sidecar filename differs from its run key")
        if record.run_key in records:
            raise ValueError("duplicate configuration-3 record run key")
        if marker.gold_sha256 != canonical_sha256(record.gold):
            raise ValueError("record sidecar gold hash mismatch")
        records[record.run_key] = record
        markers[record.run_key] = marker
    return records, markers


def _write_record_sidecar(
    path: Path,
    record: EvaluationRecord,
    *,
    execution: ProviderTaskExecution,
    raw_bundle_key: str,
) -> None:
    """Write one immutable record plus a hash marker, refusing replacement."""

    rendered = record.model_dump_json(indent=2)
    marker = RecordSidecarMarker(
        run_key=record.run_key,
        record_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        gold_sha256=canonical_sha256(record.gold),
        raw_bundle_key=raw_bundle_key,
        raw_execution_sha256=canonical_sha256(execution),
        raw_request_sha256=execution.request_sha256,
    ).model_dump_json(indent=2)
    marker_path = path.with_suffix(".sha256")
    if path.exists() or marker_path.exists():
        if not path.exists() or not marker_path.exists():
            raise RuntimeError(f"incomplete immutable record sidecar {path.name}")
        if path.read_text(encoding="utf-8") != rendered or (
            marker_path.read_text(encoding="utf-8") != marker
        ):
            raise RuntimeError(f"refusing to overwrite immutable record {path.stem}")
        return
    _atomic_write(path, rendered)
    _atomic_write(marker_path, marker)


def _validate_record_raw_chain(
    *,
    records: Mapping[str, EvaluationRecord],
    markers: Mapping[str, RecordSidecarMarker],
    artifact_dir: Path,
    raw_keys_by_run_key: Mapping[str, str],
    expected_requests: Mapping[str, str],
) -> None:
    if set(records) != set(markers) or set(records) != set(raw_keys_by_run_key):
        raise ValueError("record/raw chain does not cover the expected run keys")
    for run_key, record in records.items():
        marker = markers[run_key]
        raw_key = raw_keys_by_run_key[run_key]
        if marker.raw_bundle_key != raw_key:
            raise ValueError("record sidecar names the wrong raw bundle")
        bundle = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=raw_key,
            expected_request_sha256=expected_requests[raw_key],
        )
        if bundle is None:
            raise ValueError("record sidecar has no immutable raw bundle")
        if (
            marker.raw_execution_sha256 != canonical_sha256(bundle)
            or marker.raw_request_sha256 != bundle.request_sha256
            or record.run_key != run_key
        ):
            raise ValueError("record sidecar/raw execution chain mismatch")


def _write_canonical_records(
    path: Path,
    records: Mapping[str, EvaluationRecord],
    row_order: Sequence[str],
) -> None:
    by_id = {record.instance_id: record for record in records.values()}
    ordered = [by_id[instance_id] for instance_id in row_order if instance_id in by_id]
    rendered = "".join(record.model_dump_json() + "\n" for record in ordered)
    _atomic_write(path, rendered)


def _write_progress(
    *,
    path: Path,
    freeze_hash: str,
    mode: Literal["smoke", "full", "temporal"],
    records: Mapping[str, EvaluationRecord],
    rows: Sequence[DriftInstance],
    keys: Mapping[str, str],
    interruptions: Mapping[str, str],
) -> Config3Progress:
    completed_ids = {record.instance_id for record in records.values()}
    pending = [row.instance_id for row in rows if row.instance_id not in completed_ids]
    predictions = sum(record.prediction is not None for record in records.values())
    complete = not pending and len(records) == len(rows)
    valid = complete and not interruptions and predictions > 0
    progress = Config3Progress(
        freeze_sha256=freeze_hash,
        system_id="adaptive_agent",
        run_mode=mode,
        completed_run_keys=sorted(records),
        pending_instance_ids=pending,
        interruptions=dict(interruptions),
        status="VALID" if valid else ("NOT_EVALUABLE" if complete else "IN_PROGRESS"),
    )
    if set(progress.completed_run_keys) - set(keys.values()):
        raise ValueError("progress contains a run key outside the frozen row set")
    _atomic_write(path, progress.model_dump_json(indent=2))
    return progress


def run_config3_adaptive(
    *,
    rows: Sequence[DriftInstance],
    mode: Literal["smoke", "full", "temporal"],
    freeze: Config3RunFreeze,
    output_dir: Path = OUTPUT_DIR,
    max_workers: int = DEFAULT_MAX_WORKERS,
    distro: str = DEFAULT_WSL_DISTRO,
    codex_binary: str = DEFAULT_CODEX_BINARY,
    transport: Literal["collaboration_subagent", "wsl", "native"] | None = None,
    native_codex_binary: str | None = None,
    entailer: Entailer | None = None,
    execution_function: Callable[..., CodexTaskExecution] | None = None,
) -> tuple[list[EvaluationRecord], Config3Progress]:
    """Run isolated adaptive cases concurrently; finalize only in coordinator."""

    if max_workers != freeze.max_workers:
        raise ValueError("max_workers differs from the frozen run identity")
    transport = transport or freeze.transport
    if transport != freeze.transport:
        raise ValueError("transport differs from the frozen run identity")
    expected_order = (
        freeze.smoke_instance_ids
        if mode == "smoke"
        else (freeze.test_order if mode == "full" else freeze.t6_order)
    )
    actual_order = tuple(row.instance_id for row in rows)
    if actual_order != tuple(expected_order):
        raise ValueError("requested rows differ from the frozen row order")
    if mode in {"full", "temporal"}:
        require_full_smoke_readiness(
            output_dir=Path(output_dir),
            freeze=freeze,
            system_id="adaptive_agent",
        )
    freeze_hash = ensure_frozen_identity(
        freeze_path_for_transport(output_dir=Path(output_dir), transport=transport),
        freeze,
    )
    commit = repository_commit(ROOT)
    if commit != freeze.repository_commit:
        raise RuntimeError("repository commit differs from configuration-3 freeze")
    source_snapshot = runtime_source_sha256(ROOT)
    if source_snapshot != freeze.runtime_source_sha256:
        raise RuntimeError(
            "runtime source snapshot differs from configuration-3 freeze"
        )
    validate_phase5_baseline_identity(freeze)
    collaboration = transport == "collaboration_subagent"
    selected_execution: Callable[..., CodexTaskExecution] | None = None
    if collaboration:
        if execution_function is not None:
            raise ValueError(
                "collaboration_subagent accepts sealed external submissions, "
                "not a Codex execution function"
            )
        support_root = str(ROOT)
        tool_command = "python -m cobol_archaeologist.eval.codex_tool"
    elif transport == "native":
        from cobol_archaeologist.eval.codex_native import (
            execute_codex_task_native,
            native_chatgpt_account_sha256,
            native_codex_version,
            native_login_status,
            native_tool_command,
        )

        selected_binary = native_codex_binary or shutil.which("codex.exe")
        if selected_binary is None:
            raise RuntimeError("native codex.exe is not installed")
        login = native_login_status(selected_binary)
        account_sha256 = native_chatgpt_account_sha256()
        cli_version = native_codex_version(selected_binary)
        if freeze.wsl_distribution != "native-windows":
            raise RuntimeError("freeze execution environment is not native-windows")
        support_root = str(ROOT)
        tool_command = native_tool_command()
        selected_execution = execution_function or execute_codex_task_native
        codex_binary = selected_binary
        distro = "native-windows"
    else:
        login = _check_chatgpt_login(codex_binary=codex_binary, distro=distro)
        account_sha256 = _wsl_chatgpt_account_sha256(distro=distro)
        version = _wsl([codex_binary, "--version"], distro=distro)
        _require_ok(version, "read Codex CLI version")
        cli_version = version.stdout.decode("utf-8", errors="replace").strip()
        if freeze.wsl_distribution != distro:
            raise RuntimeError("WSL distribution differs from configuration-3 freeze")
        support_root = prepare_support_runtime(
            commit=source_snapshot,
            distro=distro,
        )
        tool_command = (
            f"{support_root}/.venv/bin/python -m cobol_archaeologist.eval.codex_tool"
        )
        selected_execution = execution_function or execute_codex_task
    if not collaboration:
        if codex_binary != freeze.codex_binary:
            raise RuntimeError("Codex binary differs from configuration-3 freeze")
        if "ChatGPT" not in login:
            raise RuntimeError("ChatGPT authentication is required")
        if account_sha256 != freeze.chatgpt_account_sha256:
            raise RuntimeError("ChatGPT account differs from configuration-3 freeze")
        if cli_version != freeze.codex_cli_version:
            raise RuntimeError("Codex CLI version differs from configuration-3 freeze")
    if mode == "temporal":
        t6_path = ROOT / freeze.t6_v2_path
        if hashlib.sha256(t6_path.read_bytes()).hexdigest() != freeze.t6_v2_sha256:
            raise RuntimeError("finalized T6 manifest differs from the freeze")
        finalized, finalized_rows = load_finalized_t6_rows(
            root=ROOT, manifest_path=t6_path
        )
        if (
            tuple(row.instance_id for row in finalized_rows) != freeze.t6_order
            or finalized.source_inputs != freeze.t6_source_inputs
        ):
            raise RuntimeError("finalized T6 rows/source inputs differ from freeze")
    materialized: dict[str, MaterializedSource] = {
        row.instance_id: (
            materialize_finalized_t6_row(
                row,
                root=ROOT,
                source_inputs=freeze.t6_source_inputs,
            )
            if mode == "temporal"
            else materialize(row)
        )
        for row in rows
    }
    for row in rows:
        expected_sha = freeze.source_sha256.get(row.instance_id)
        actual_sha = materialized[row.instance_id].source_sha256
        if expected_sha != actual_sha:
            raise RuntimeError(f"source hash differs from freeze for {row.instance_id}")
    keys = {
        row.instance_id: config3_run_key(
            freeze=freeze,
            system_id="adaptive_agent",
            run_mode=mode,
            instance_id=row.instance_id,
            source_sha256=materialized[row.instance_id].source_sha256,
        )
        for row in rows
    }
    artifact_dir = Path(output_dir) / mode / "adaptive_agent"
    sidecar_dir = artifact_dir / "records"
    schema = strict_codex_schema(CodexAdaptiveEnvelope)
    staging_base = artifact_dir / COLLABORATION_STAGING_DIRECTORY
    staged_tasks: dict[str, StagedCollaborationTask] = {}
    if collaboration:
        staged_tasks = {
            keys[row.instance_id]: stage_collaboration_task(
                staging_base=staging_base,
                run_key=keys[row.instance_id],
                sources={"drift_900000": materialized[row.instance_id]},
                authorized_hunts=(ADAPTIVE_HUNT,),
            )
            for row in rows
        }
    prompts = {
        row.instance_id: build_adaptive_codex_prompt(
            alias="drift_900000",
            clause=row.regulation_clause,
            program_scope=Path(row.provenance.base_program).stem,
            tool_command=(
                staged_tasks[keys[row.instance_id]].tool_command
                if collaboration
                else tool_command
            ),
        )
        for row in rows
    }
    collaboration_requests = {}
    if collaboration:
        group_id = f"config3:{mode}:adaptive_agent"
        for ordinal, row in enumerate(rows, start=1):
            key = keys[row.instance_id]
            request = build_collaboration_request(
                run_key=key,
                prompt=prompts[row.instance_id],
                schema=schema,
                sources={"drift_900000": materialized[row.instance_id]},
                runtime_source_sha256=freeze.runtime_source_sha256,
                authorized_hunts=(ADAPTIVE_HUNT,),
                visible_cases=1,
                group=CollaborationGroupIdentity(
                    group_id=group_id,
                    mode="concurrent" if len(rows) > 1 else "sequential",
                    ordinal=ordinal,
                    size=len(rows),
                ),
            )
            ensure_collaboration_request(
                artifact_dir / COLLABORATION_STAGED_REQUEST_DIRECTORY / f"{key}.json",
                request,
            )
            collaboration_requests[key] = request
        expected_requests = {
            key: request.request_sha256
            for key, request in collaboration_requests.items()
        }
    else:
        expected_requests = {
            keys[row.instance_id]: expected_codex_request_sha256(
                prompt=prompts[row.instance_id],
                schema=schema,
                sources={"drift_900000": materialized[row.instance_id]},
                transport=transport,
                codex_binary=codex_binary,
                runtime_source_sha256=freeze.runtime_source_sha256,
                chatgpt_account_sha256=freeze.chatgpt_account_sha256,
                authorized_hunts=(ADAPTIVE_HUNT,),
            )
            for row in rows
        }
    records, sidecar_markers = _load_record_sidecars(sidecar_dir)
    unexpected = set(records) - set(keys.values())
    if unexpected:
        raise ValueError("record sidecars contain stale or unexpected run keys")
    by_key = {value: instance_id for instance_id, value in keys.items()}
    for key, record in records.items():
        instance_id = by_key[key]
        if (
            record.system_id != "adaptive_agent"
            or record.instance_id != instance_id
            or record.source_sha256 != materialized[instance_id].source_sha256
            or record.gold
            != next(row for row in rows if row.instance_id == instance_id)
        ):
            raise ValueError("record sidecar identity differs from the frozen request")
    if records:
        _validate_record_raw_chain(
            records=records,
            markers=sidecar_markers,
            artifact_dir=artifact_dir,
            raw_keys_by_run_key={key: key for key in records},
            expected_requests=expected_requests,
        )
    interruptions: dict[str, str] = {}
    entailer = entailer or default_entailer()

    def finalize(row: DriftInstance, execution: ProviderTaskExecution) -> None:
        key = keys[row.instance_id]
        envelope = CodexAdaptiveEnvelope.model_validate_json(execution.final_message)
        submitted = envelope.results[0]
        if submitted.alias != "drift_900000":
            raise ValueError("adaptive task returned the wrong opaque alias")
        with tempfile.TemporaryDirectory(prefix="m4-config3-verify-") as temp:
            tools = _tool_layer(materialized[row.instance_id], Path(temp), None)
            outcome = finalize_adaptive_case(
                submitted,
                clause=row.regulation_clause,
                program_scope=Path(row.provenance.base_program).stem,
                instance_id=row.instance_id,
                logs=execution.tool_logs,
                tools=tools,
                entailer=entailer,
                token_count=(
                    execution.parsed.usage.total_tokens
                    if execution.parsed.usage is not None
                    else 0
                ),
                token_count_recorded=execution.parsed.usage is not None,
            )
        record = _record_adaptive_outcome(
            row,
            outcome,
            source_sha256=materialized[row.instance_id].source_sha256,
            key=key,
        )
        _write_record_sidecar(
            sidecar_dir / f"{key}.json",
            record,
            execution=execution,
            raw_bundle_key=key,
        )
        records[key] = record

    pending: list[DriftInstance] = []
    for row in rows:
        key = keys[row.instance_id]
        if key in records:
            continue
        bundle = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=key,
            expected_request_sha256=expected_requests[key],
        )
        if bundle is not None:
            validate_staged_collaboration_execution(
                bundle,
                staged=staged_tasks[key],
                staging_base=staging_base,
            )
            finalize(row, bundle)
        else:
            pending.append(row)

    def execute(row: DriftInstance) -> CodexTaskExecution:
        if selected_execution is None:
            raise RuntimeError(
                "collaboration_subagent results must be ingested and sealed externally"
            )
        return selected_execution(
            prompt=prompts[row.instance_id],
            schema=schema,
            sources={"drift_900000": materialized[row.instance_id]},
            support_root=support_root,
            distro=distro,
            codex_binary=codex_binary,
            model_id=MODEL_ID,
            reasoning_effort=REASONING_EFFORT,
            timeout_s=CONFIG3_AGENT_BUDGET.wall_clock_timeout_s,
            runtime_source_sha256=freeze.runtime_source_sha256,
            authentication_identity_sha256=freeze.chatgpt_account_sha256,
            authorized_hunts=(ADAPTIVE_HUNT,),
        )

    progress_path = artifact_dir / "progress.json"
    records_path = artifact_dir / "adaptive_agent.jsonl"
    _write_progress(
        path=progress_path,
        freeze_hash=freeze_hash,
        mode=mode,
        records=records,
        rows=rows,
        keys=keys,
        interruptions=interruptions,
    )
    if collaboration:
        _write_canonical_records(records_path, records, actual_order)
        progress = _write_progress(
            path=progress_path,
            freeze_hash=freeze_hash,
            mode=mode,
            records=records,
            rows=rows,
            keys=keys,
            interruptions=interruptions,
        )
        if mode == "smoke":
            refresh_smoke_readiness(output_dir=Path(output_dir), freeze=freeze)
        return (
            sorted(
                records.values(),
                key=lambda record: actual_order.index(record.instance_id),
            ),
            progress,
        )
    for row, execution_result, error in bounded_provider_map(
        pending,
        execute,
        max_workers=max_workers,
    ):
        key = keys[row.instance_id]
        if error is not None or execution_result is None:
            interruptions[row.instance_id] = (
                f"{type(error).__name__}: {error}" if error is not None else "unknown"
            )
        else:
            persist_execution_bundle(
                execution_result,
                artifact_dir=artifact_dir,
                key=key,
                expected_request_sha256=expected_requests[key],
            )
            try:
                finalize(row, execution_result)
                interruptions.pop(row.instance_id, None)
            except Exception as exc:  # noqa: BLE001
                interruptions[row.instance_id] = (
                    f"finalization {type(exc).__name__}: {exc}"
                )
        _write_canonical_records(records_path, records, actual_order)
        progress = _write_progress(
            path=progress_path,
            freeze_hash=freeze_hash,
            mode=mode,
            records=records,
            rows=rows,
            keys=keys,
            interruptions=interruptions,
        )
        print(
            json.dumps(
                {
                    "system": "adaptive_agent",
                    "mode": mode,
                    "completed": len(records),
                    "total": len(rows),
                    "pending": len(progress.pending_instance_ids),
                    "interruptions": len(interruptions),
                }
            ),
            flush=True,
        )
    _write_canonical_records(records_path, records, actual_order)
    progress = _write_progress(
        path=progress_path,
        freeze_hash=freeze_hash,
        mode=mode,
        records=records,
        rows=rows,
        keys=keys,
        interruptions=interruptions,
    )
    if mode == "smoke":
        refresh_smoke_readiness(output_dir=Path(output_dir), freeze=freeze)
    elif mode == "temporal" and progress.status == "VALID":
        write_temporal_score(output_dir=Path(output_dir), freeze=freeze)
    ordered_records = sorted(
        records.values(),
        key=lambda record: actual_order.index(record.instance_id),
    )
    return ordered_records, progress
