"""Frozen T5.5A panel and single-component ablation definitions.

This module contains only pre-result experiment identity.  Provider execution
is delegated to :mod:`cobol_archaeologist.eval.codex_live` after the definition
files have been committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.eval.live import ROOT, SPLIT, load_split
from cobol_archaeologist.eval.schemas import EvaluationRecord, RunValidity
from cobol_archaeologist.schemas import DriftInstance

EXPERIMENT_ID = "t5.5a-core-ablation-supplement-v1"
PANEL_SEED = 20260823
BOOTSTRAP_SEED = 550123
BOOTSTRAP_RESAMPLES = 10_000
PANEL_ROWS = 71
SMOKE_ROWS = 7
PANEL_PATH = ROOT / "data" / "eval" / "m5" / "ablations" / "panel.json"
DEFINITION_PATH = (
    ROOT / "data" / "eval" / "m5" / "ablations" / "definition.json"
)
OUTPUT_ROOT = ROOT / "data" / "eval" / "m5" / "ablations"

ConfigurationID = Literal[
    "control",
    "no_slicing",
    "no_execution",
    "no_entailment",
    "no_reranking",
]


class AblationDefinition(BaseModel):
    """One frozen runtime configuration relative to the control."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configuration_id: ConfigurationID
    removed_component: str | None
    disabled_tools: tuple[str, ...] = ()
    execution_verification: bool = True
    entailment_verification: bool = True
    regulation_search_mode: Literal["hybrid", "hybrid_rerank"] = "hybrid_rerank"


CONFIGURATIONS: dict[ConfigurationID, AblationDefinition] = {
    "control": AblationDefinition(
        configuration_id="control",
        removed_component=None,
    ),
    "no_slicing": AblationDefinition(
        configuration_id="no_slicing",
        removed_component="program_slicing",
        disabled_tools=("slice_on",),
    ),
    "no_execution": AblationDefinition(
        configuration_id="no_execution",
        removed_component="cobol_execution_grounding",
        disabled_tools=("run_cobol",),
        execution_verification=False,
    ),
    "no_entailment": AblationDefinition(
        configuration_id="no_entailment",
        removed_component="entailment_acceptance_gate",
        entailment_verification=False,
    ),
    "no_reranking": AblationDefinition(
        configuration_id="no_reranking",
        removed_component="cross_encoder_reranking",
        regulation_search_mode="hybrid",
    ),
}
CONFIGURATION_IDS: tuple[ConfigurationID, ...] = tuple(CONFIGURATIONS)

# DECISION (T5.5A ratification): frozen retrieval has no detachable temporal
# filter. A synthetic filtered control or metadata-hiding prompt would change
# more than one frozen component, so versioning is documented but not run.
VERSIONING_DISPOSITION = {
    "status": "NOT_INDEPENDENTLY_ABLATABLE",
    "reason": (
        "Temporal identity is embedded in the benchmark-supplied RegulationClause "
        "and prompt contract. The frozen T5.4 architecture has no independent "
        "runtime version/effective-date retrieval filter whose removal leaves all "
        "other components unchanged."
    ),
    "regulation_search_behavior": (
        "RegulationSearch searches the complete corpus/index and maps chunk hits "
        "to clauses by (doc, clause_id); its API accepts no version or "
        "effective-date filter."
    ),
    "prompt_behavior": (
        "build_hunt_prompt exposes clause.version and clause.effective_date from "
        "the exact benchmark-supplied RegulationClause."
    ),
    "excluded_substitutions": [
        "Adding a filtered control would violate frozen T5.4 control identity.",
        (
            "Hiding temporal metadata would be a distinct prompt/input ablation "
            "and could violate the frozen RegulationClause contract."
        ),
    ],
    "claim_limit": "The contribution of version awareness is not experimentally estimated.",
}


def _rank(seed: int, namespace: str, instance_id: str) -> str:
    return hashlib.sha256(f"{seed}:{namespace}:{instance_id}".encode()).hexdigest()


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class AblationPanel(BaseModel):
    """Committed 71-row paired panel and seven-row validity-only smoke."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    seed: int
    selection_method: str
    split_path: str
    split_sha256_lf: str = Field(pattern=r"^[0-9a-f]{64}$")
    instance_ids: list[str]
    smoke_instance_ids: list[str]
    distribution: dict[str, Any]
    versioning_disposition: dict[str, Any]
    identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _frozen_shape(self) -> AblationPanel:
        if self.experiment_id != EXPERIMENT_ID or self.seed != PANEL_SEED:
            raise ValueError("panel experiment identity or seed is not frozen")
        if len(self.instance_ids) != PANEL_ROWS or len(set(self.instance_ids)) != PANEL_ROWS:
            raise ValueError("ablation panel requires 71 unique IDs")
        if len(self.smoke_instance_ids) != SMOKE_ROWS or len(
            set(self.smoke_instance_ids)
        ) != SMOKE_ROWS:
            raise ValueError("ablation smoke requires seven unique IDs")
        if not set(self.smoke_instance_ids) <= set(self.instance_ids):
            raise ValueError("smoke IDs must be members of the panel")
        payload = self.model_dump(exclude={"identity_sha256"})
        if self.identity_sha256 != _canonical_json_sha256(payload):
            raise ValueError("panel identity hash mismatch")
        return self


def select_panel(
    rows: Sequence[DriftInstance],
    *,
    split_path: Path = SPLIT,
    seed: int = PANEL_SEED,
) -> AblationPanel:
    """Select only from frozen gold class/locus strata, never prior outcomes."""

    if seed != PANEL_SEED:
        raise ValueError(f"T5.5A panel seed is {PANEL_SEED}, not {seed}")
    ordered = list(rows)
    ids = [row.instance_id for row in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("frozen split contains duplicate IDs")
    interprocedural = [row for row in ordered if row.code_locus.is_interprocedural]
    if len(interprocedural) != 36:
        raise ValueError(
            f"frozen panel requires 36 interprocedural rows, found {len(interprocedural)}"
        )
    chosen = {row.instance_id for row in interprocedural}
    local_selected: dict[str, list[str]] = {}
    for drift_type in sorted({row.drift_type for row in ordered}):
        candidates = [
            row
            for row in ordered
            if row.drift_type == drift_type and not row.code_locus.is_interprocedural
        ]
        if len(candidates) < 5:
            raise ValueError(f"{drift_type} has fewer than five local rows")
        selected = sorted(
            candidates,
            key=lambda row: (_rank(seed, f"panel:{drift_type}", row.instance_id), row.instance_id),
        )[:5]
        local_selected[drift_type] = [row.instance_id for row in selected]
        chosen.update(local_selected[drift_type])
    panel_rows = [row for row in ordered if row.instance_id in chosen]
    if len(panel_rows) != PANEL_ROWS:
        raise ValueError(f"panel selector produced {len(panel_rows)} rows")
    smoke_chosen = {
        min(
            (row for row in panel_rows if row.drift_type == drift_type),
            key=lambda row: (_rank(seed, f"smoke:{drift_type}", row.instance_id), row.instance_id),
        ).instance_id
        for drift_type in sorted({row.drift_type for row in panel_rows})
    }
    smoke_ids = [row.instance_id for row in panel_rows if row.instance_id in smoke_chosen]
    class_locus = Counter(
        (row.drift_type, "interprocedural" if row.code_locus.is_interprocedural else "local")
        for row in panel_rows
    )
    payload: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "seed": seed,
        "selection_method": (
            "Include all interprocedural rows. Within each D1-D7 local stratum, "
            "rank IDs by SHA-256(seed:panel:class:instance_id), select five, then "
            "restore frozen v1 order. Select one smoke row per class by the "
            "analogous seed:smoke:class rank and preserve panel order."
        ),
        "split_path": split_path.relative_to(ROOT).as_posix(),
        "split_sha256_lf": hashlib.sha256(split_path.read_bytes()).hexdigest(),
        "instance_ids": [row.instance_id for row in panel_rows],
        "smoke_instance_ids": smoke_ids,
        "distribution": {
            "total": len(panel_rows),
            "locus": {
                "interprocedural": len(interprocedural),
                "local": len(panel_rows) - len(interprocedural),
            },
            "by_class_and_locus": {
                drift_type: {
                    "interprocedural": class_locus[(drift_type, "interprocedural")],
                    "local": class_locus[(drift_type, "local")],
                    "total": class_locus[(drift_type, "interprocedural")]
                    + class_locus[(drift_type, "local")],
                }
                for drift_type in sorted({row.drift_type for row in panel_rows})
            },
            "smoke_by_class": dict(
                sorted(Counter(row.drift_type for row in panel_rows if row.instance_id in smoke_chosen).items())
            ),
        },
        "versioning_disposition": VERSIONING_DISPOSITION,
    }
    return AblationPanel(
        **payload,
        identity_sha256=_canonical_json_sha256(payload),
    )


def definition_payload(panel: AblationPanel) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "panel_identity_sha256": panel.identity_sha256,
        "panel_seed": PANEL_SEED,
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "interval": "paired percentile 95%",
            "delta": "F1(ablation) - F1(control)",
        },
        "provider_plan": {
            "configurations": list(CONFIGURATION_IDS),
            "smoke_rows_per_configuration": SMOKE_ROWS,
            "full_rows_per_configuration": PANEL_ROWS,
            "maximum_provider_rows": len(CONFIGURATION_IDS) * (SMOKE_ROWS + PANEL_ROWS),
            "performance_is_not_a_smoke_gate": True,
        },
        "configurations": {
            key: value.model_dump(mode="json") for key, value in CONFIGURATIONS.items()
        },
        "versioning_disposition": VERSIONING_DISPOSITION,
        "output_paths": {
            key: f"data/eval/m5/ablations/{key}/" for key in CONFIGURATION_IDS
        },
        "frozen_control": {
            "model_id": "gpt-5.6-luna",
            "reasoning_effort": "low",
            "prompt_version": "m4-live-codex-batch-v4",
            "action_budget": "AGENT_BUDGET",
            "schema_version": "3",
            "provider_mechanism": "ChatGPT-authenticated Codex CLI",
        },
    }
    return {**payload, "identity_sha256": _canonical_json_sha256(payload)}


def write_definition() -> tuple[AblationPanel, dict[str, Any]]:
    panel = select_panel(load_split())
    definition = definition_payload(panel)
    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    PANEL_PATH.write_text(panel.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    DEFINITION_PATH.write_text(
        json.dumps(definition, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return panel, definition


def load_frozen_panel() -> AblationPanel:
    panel = AblationPanel.model_validate_json(PANEL_PATH.read_text(encoding="utf-8"))
    expected = select_panel(load_split())
    if panel != expected:
        raise ValueError("committed T5.5A panel does not reproduce from frozen v1")
    return panel


def assert_definition_committed() -> str:
    """Provider execution is forbidden while any definition input is dirty."""

    paths = (
        "src/cobol_archaeologist",
        "tests/test_ablations.py",
        "docs/tasks/T5.5A-work-order.md",
        "data/eval/m5/ablations/panel.json",
        "data/eval/m5/ablations/definition.json",
        "STATUS.md",
        ".gitignore",
    )
    dirty: list[str] = []
    for cached in (False, True):
        command = ["git", "diff", "--name-only", "--ignore-cr-at-eol"]
        if cached:
            command.append("--cached")
        command.extend(("--", *paths))
        result = subprocess.run(command, cwd=ROOT, capture_output=True, check=True, text=True)
        dirty.extend(result.stdout.splitlines())
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *paths],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    dirty.extend(untracked.stdout.splitlines())
    if dirty:
        raise RuntimeError(
            "T5.5A provider execution requires a committed experiment definition:\n"
            + "\n".join(sorted(set(filter(None, dirty))))
        )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


class DisabledAblationTool(RuntimeError):
    """A declared component was requested but was not executed."""


class AblatedToolLayer:
    """Transparent ToolLayer proxy that blocks only declared tools."""

    def __init__(self, inner: Any, disabled_tools: Sequence[str]) -> None:
        self._inner = inner
        self._disabled_tools = frozenset(disabled_tools)

    def __getattr__(self, name: str) -> Any:
        if name in self._disabled_tools:
            raise DisabledAblationTool(f"{name} disabled by frozen T5.5A configuration")
        return getattr(self._inner, name)


def assess_ablation_validity(
    records: Sequence[EvaluationRecord],
    *,
    expected_rows: int,
) -> RunValidity:
    """Validity-only gate; prediction rate and scientific scores never gate."""

    infrastructure = sum(record.infrastructure_error is not None for record in records)
    trajectories = [
        trace.trajectory
        for record in records
        if not record.infrastructure_error
        for trace in record.agent_hunts
    ]
    responses = [response for trace in trajectories for response in trace.model_responses]
    contract_rejections = sum(response.contract_error is not None for response in responses)
    available = len(records) - infrastructure
    predictions = sum(
        record.prediction is not None
        for record in records
        if record.infrastructure_error is None
    )
    successful_tools = sum(
        call.error is None and bool(call.observation_summary)
        for trace in trajectories
        for call in trace.steps
    )
    failed: list[str] = []
    if len(records) != expected_rows:
        failed.append(f"completed {len(records)} of {expected_rows} required rows")
    if infrastructure:
        failed.append(f"{infrastructure} infrastructure/schema failure(s); zero required")
    if contract_rejections:
        failed.append(f"{contract_rejections} contract-rejection response(s); zero required")
    return RunValidity(
        completed_rows=len(records),
        available_rows=available,
        infrastructure_failures=infrastructure,
        provider_turns=len(responses),
        contract_rejections=contract_rejections,
        contract_rejection_rate=(contract_rejections / len(responses) if responses else 0.0),
        non_null_predictions=predictions,
        non_null_prediction_rate=predictions / available if available else 0.0,
        successful_tool_observations=successful_tools,
        mean_successful_tool_observations=(successful_tools / available if available else 0.0),
        status="VALID" if not failed else "NOT_EVALUABLE",
        failed_gates=failed,
    )


def singleton_schema_retries[T](
    batch: Sequence[T],
    *,
    repair_attempt: int,
    max_repairs: int,
) -> list[tuple[list[T], int]] | None:
    """Return the frozen M4 singleton fallback for a malformed batch envelope."""

    if len(batch) <= 1 or repair_attempt >= max_repairs:
        return None
    return [([row], repair_attempt + 1) for row in batch]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-definition", action="store_true")
    parser.add_argument("--configuration", choices=CONFIGURATION_IDS)
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.freeze_definition:
        panel, definition = write_definition()
        print(
            json.dumps(
                {
                    "panel": str(PANEL_PATH.relative_to(ROOT)),
                    "panel_identity": panel.identity_sha256,
                    "definition_identity": definition["identity_sha256"],
                }
            )
        )
        return 0
    if args.configuration is None:
        raise SystemExit("--configuration is required unless --freeze-definition is used")
    assert_definition_committed()
    from cobol_archaeologist.eval.codex_live import run_codex_ablation

    run_codex_ablation(args.configuration, mode=args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
