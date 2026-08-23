"""Permanent offline gates for the frozen T5.5A experiment definition."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from cobol_archaeologist.eval.ablation_report import _paired
from cobol_archaeologist.eval.ablations import (
    BOOTSTRAP_RESAMPLES,
    CONFIGURATION_IDS,
    CONFIGURATIONS,
    DEFINITION_PATH,
    PANEL_PATH,
    PANEL_SEED,
    VERSIONING_DISPOSITION,
    AblatedToolLayer,
    AblationPanel,
    DisabledAblationTool,
    assess_ablation_validity,
    load_frozen_panel,
    select_panel,
    singleton_schema_retries,
)
from cobol_archaeologist.eval.codex_tool import ToolRequest, execute_tool_request
from cobol_archaeologist.eval.live import load_split
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model import verify as verify_module
from cobol_archaeologist.model.prompt import build_hunt_prompt
from cobol_archaeologist.model.verify import (
    NLI_CACHE,
    CachedEntailer,
    Finding,
    VerificationTier,
    verify,
)
from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.tools import RealToolLayer

ROOT = Path(__file__).resolve().parents[1]
VERIFY_FIXTURES = ROOT / "tests" / "fixtures" / "verify"


def _finding(name: str) -> Finding:
    return Finding.model_validate_json(
        (VERIFY_FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    )


def test_panel_reproduces_exact_frozen_identity_and_distribution() -> None:
    committed = AblationPanel.model_validate_json(PANEL_PATH.read_text(encoding="utf-8"))
    assert committed == select_panel(load_split(), seed=PANEL_SEED)
    assert committed == load_frozen_panel()
    assert committed.split_sha256_lf == (
        "bc9e775a727d82c7d5a30fd0495512bffde173bec2580e3d08664b8d98b2aed4"
    )
    assert committed.identity_sha256 == (
        "7882a07d8fe656b227eae80fc861a14a84fb53a0a5e4bc4b9f5f62db510f52c2"
    )
    assert committed.distribution["locus"] == {
        "interprocedural": 36,
        "local": 35,
    }
    assert all(
        values["local"] == 5
        for values in committed.distribution["by_class_and_locus"].values()
    )
    assert set(committed.distribution["smoke_by_class"].values()) == {1}


def test_definition_has_five_provider_configs_and_no_versioning_run() -> None:
    definition = json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))
    assert tuple(definition["provider_plan"]["configurations"]) == CONFIGURATION_IDS
    assert definition["provider_plan"]["maximum_provider_rows"] == 390
    assert definition["bootstrap"]["resamples"] == BOOTSTRAP_RESAMPLES == 10_000
    assert "no_versioning" not in definition["configurations"]
    assert VERSIONING_DISPOSITION["status"] == "NOT_INDEPENDENTLY_ABLATABLE"


def test_versioning_disposition_matches_frozen_architecture() -> None:
    search_parameters = inspect.signature(RegulationSearch.search).parameters
    assert "version" not in search_parameters
    assert "effective_date" not in search_parameters
    row = load_split()[0]
    prompt = build_hunt_prompt(
        row.drift_type,
        row.regulation_clause,
        Path(row.provenance.base_program).stem,
    )
    assert f"version {row.regulation_clause.version}" in prompt
    assert f"effective {row.regulation_clause.effective_date}" in prompt


def test_each_executable_ablation_changes_only_its_declared_component() -> None:
    control = CONFIGURATIONS["control"]
    assert CONFIGURATIONS["no_slicing"].model_copy(
        update={"configuration_id": "control", "removed_component": None, "disabled_tools": ()}
    ) == control
    assert CONFIGURATIONS["no_execution"].model_copy(
        update={
            "configuration_id": "control",
            "removed_component": None,
            "disabled_tools": (),
            "execution_verification": True,
        }
    ) == control
    assert CONFIGURATIONS["no_entailment"].model_copy(
        update={
            "configuration_id": "control",
            "removed_component": None,
            "entailment_verification": True,
        }
    ) == control
    assert CONFIGURATIONS["no_reranking"].model_copy(
        update={
            "configuration_id": "control",
            "removed_component": None,
            "regulation_search_mode": "hybrid_rerank",
        }
    ) == control


def test_disabled_tool_proxy_blocks_only_declared_tool() -> None:
    class Tools:
        def slice_on(self) -> str:
            return "slice"

        def grep(self) -> str:
            return "grep"

    tools = AblatedToolLayer(Tools(), ("slice_on",))
    with pytest.raises(DisabledAblationTool, match="slice_on disabled"):
        tools.slice_on()
    assert tools.grep() == "grep"


def test_codex_tool_bridge_records_disabled_call_without_invoking_it(tmp_path: Path) -> None:
    source = tmp_path / "cases" / "drift_900000"
    source.mkdir(parents=True)
    (tmp_path / "descriptor.json").write_text(
        json.dumps(
            {
                "aliases": {"drift_900000": {"source_dir": "cases/drift_900000"}},
                "ablation_runtime": {
                    "disabled_tools": ["slice_on"],
                    "regulation_search_mode": "hybrid_rerank",
                },
            }
        ),
        encoding="utf-8",
    )

    class ForbiddenTools:
        def slice_on(self, **_arguments):
            raise AssertionError("program slicer must not execute")

    entry = execute_tool_request(
        ToolRequest(
            alias="drift_900000",
            hunt="D1_stale_threshold",
            tool="slice_on",
            arguments={"var": "X"},
        ),
        task_root=tmp_path,
        tool_factory=lambda _source: ForbiddenTools(),
    )
    assert entry.error == "RuntimeError: slice_on disabled by frozen T5.5A configuration"


def test_no_entailment_bypasses_only_entailment_acceptance() -> None:
    tools = RealToolLayer(
        corpus_root=VERIFY_FIXTURES / "corpus",
        copybook_paths=[],
    )
    entailer = CachedEntailer(cache_path=NLI_CACHE, require_cache=True)
    normal = verify(_finding("unsupported_citation"), tools, entailer=entailer)
    ablated = verify(
        _finding("unsupported_citation"),
        tools,
        entailer=entailer,
        entailment_verification=False,
    )
    assert normal.verified is False and normal.citation_ok is False
    assert ablated.verified is True
    assert ablated.tier == VerificationTier.STATIC
    assert ablated.citation_ok is True
    assert ablated.entailment_probability is None
    assert all(attempt.tier != VerificationTier.ENTAILMENT for attempt in ablated.tier_attempts)


def test_no_execution_skips_trusted_execution_tier(monkeypatch) -> None:
    tools = RealToolLayer(
        corpus_root=VERIFY_FIXTURES / "corpus",
        copybook_paths=[],
    )
    entailer = CachedEntailer(cache_path=NLI_CACHE, require_cache=True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("execution verifier must not run")

    monkeypatch.setattr(verify_module, "_tier1_executed", forbidden)
    result = verify(
        _finding("supported_tier2"),
        tools,
        entailer=entailer,
        execution_verification=False,
    )
    assert result.verified and result.tier == VerificationTier.STATIC
    assert result.tier_attempts[0].detail == "Tier-1 execution disabled by frozen ablation"


def test_validity_gate_does_not_gate_on_scientific_performance() -> None:
    validity = assess_ablation_validity([], expected_rows=0)
    assert validity.status == "VALID"
    assert validity.non_null_prediction_rate == 0.0


def test_malformed_multirow_envelope_uses_frozen_singleton_fallback() -> None:
    assert singleton_schema_retries(
        ["a", "b"], repair_attempt=0, max_repairs=2
    ) == [(["a"], 1), (["b"], 1)]
    assert singleton_schema_retries(
        ["a"], repair_attempt=0, max_repairs=2
    ) is None
    assert singleton_schema_retries(
        ["a", "b"], repair_attempt=2, max_repairs=2
    ) is None


def test_paired_report_uses_ablation_minus_control_sign() -> None:
    records_path = ROOT / "data" / "eval" / "m5" / "agent-rerun" / "agent.jsonl"
    records = [
        EvaluationRecord.model_validate_json(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()[:3]
    ]
    comparison = _paired(records, records, "overall")
    assert comparison["delta_f1_ablation_minus_control"] == 0.0
    assert comparison["paired_bootstrap_95_ci"] == [0.0, 0.0]
    assert comparison["bootstrap_resamples"] == 10_000
