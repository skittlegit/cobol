from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.benchmark import t6_replacement as replacement_protocol
from cobol_archaeologist.benchmark.t6_pair_correction import (
    PairCorrectionAuditManifest,
    PairCorrectionPlanItem,
)
from cobol_archaeologist.benchmark.t6_replacement import (
    REPLACEMENT_ORDER,
    ReplacementCompletion,
    ReplacementPlanItem,
    build_replacement_prompt,
    require_replacement_flip,
)
from cobol_archaeologist.benchmark.t6_review import ReviewResponse
from scripts.prepare_t6_replacements import prepare

ROOT = Path(__file__).resolve().parents[1]
REPLACEMENT_ROOT = ROOT / "data/benchmark/t6-v2/replacements"
REVIEW_V2 = REPLACEMENT_ROOT / "review-v2"
REVIEW_V3 = REPLACEMENT_ROOT / "review-v3"
FROZEN_REVIEW = REPLACEMENT_ROOT / "review-v4"
FROZEN_MANIFEST_SHA256 = (
    "072373e6dccf11982f54fc027e5491cb5e1bd3d8ed2b570b4293cb4fee3518e0"
)
DIAGNOSTIC_SHA256 = "d996cde53ad6b68ebd532baab1db64c24109aed870e03e735201921cc8076c87"
DIAGNOSTIC_FINAL_SHA256 = (
    "04f6df9c90a2b1c0f36a080b26e7a4a917303c99d5895836379d765252e37543"
)
SUPERSEDED_SHA256 = "8dd25714bfd4e9a1345f0322254b2d5582105f6b5717c8a4d36285725ad726a0"
PROGRAM_ID = re.compile(r"\bPROGRAM-ID\.\s+([A-Z0-9-]+)\.", re.IGNORECASE)
CALL_TARGET = re.compile(r"\bCALL\s+['\"]([A-Z0-9-]+)['\"]", re.IGNORECASE)


@pytest.fixture()
def prepared(tmp_path: Path) -> tuple[dict[str, object], list[ReplacementPlanItem]]:
    output = tmp_path / "replacement-review"
    manifest_path = prepare(
        root=ROOT,
        output_dir=output,
        protocol_version="v3_decision_semantics",
        freeze_version="v4",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    plan_path = ROOT / manifest["replacement_plan"]["path"]
    plans = [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    return manifest, plans


def _load_review(review: Path) -> tuple[dict[str, object], list[ReplacementPlanItem]]:
    manifest = json.loads(
        (review / "prompt-manifest.coordinator-private.json").read_text(
            encoding="utf-8"
        )
    )
    plans = [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in (
            review / "replacement-plan.coordinator-private.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    return manifest, plans


def _pin_matches(pin: dict[str, str]) -> Path:
    path = (ROOT / pin["path"]).resolve()
    assert path.is_relative_to(ROOT.resolve())
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"]
    return path


def _authority_signature(sides) -> set[tuple[str, str, str, str]]:
    return {
        (
            side.authority.doc,
            side.authority.clause_id,
            side.authority.version,
            side.authority.effective_date.isoformat(),
        )
        for side in sides
    }


def _program_spans(source: str) -> dict[str, range]:
    lines = source.splitlines()
    declarations = [
        (index, match.group(1).upper())
        for index, line in enumerate(lines, start=1)
        if (match := PROGRAM_ID.search(line))
    ]
    result = {}
    for index, (start, program) in enumerate(declarations):
        end = declarations[index + 1][0] - 1 if index + 1 < len(declarations) else len(lines)
        result[program] = range(start, end + 1)
    return result


def _valid_completion(plan: ReplacementPlanItem) -> ReplacementCompletion:
    locus = plan.code_locus.loci[0]
    return ReplacementCompletion(
        review_call_id=plan.replacement_call_id,
        sides=(
            {
                "review_item_id": plan.sides[0].review_item_id,
                "review_response": {
                    "decision": "include",
                    "drift_type": "D7_conformant",
                    "line_level": [],
                    "rationale": "The visible source conforms to this authority.",
                    "uncertainty_notes": None,
                },
            },
            {
                "review_item_id": plan.sides[1].review_item_id,
                "review_response": {
                    "decision": "include",
                    "drift_type": "D1_stale_threshold",
                    "line_level": [
                        {
                            "program": locus.program,
                            "line": locus.line_span[0],
                            "source_alias": plan.sides[1].source_alias,
                        }
                    ],
                    "rationale": "The visible source implements an older rule.",
                    "uncertainty_notes": None,
                },
            },
        ),
    )


def _production_plan_validator():
    validator = getattr(
        replacement_protocol, "validate_replacement_completion", None
    )
    assert callable(validator), (
        "production replacement protocol lacks a plan-bound completion validator"
    )
    return validator


def test_model_visible_prompts_are_neutral_and_byte_deterministic(prepared) -> None:
    manifest, plans = prepared
    forbidden = (
        "replacement",
        "candidate",
        "temporal",
        "target",
        "flip",
        "proposal",
        "gold",
        "data/benchmark",
        str(ROOT).lower(),
        "c:\\",
        "one d7 and one",
        "validated_flip",
        "rejected_nonflip",
        "expected outcome",
        "correct side",
        "older authority",
        "newer authority",
    )
    decision_semantics = (
        "Decision semantics: include means the source-authority relationship is "
        "usable and confidently classifiable as D1-D7, including D7 conformant; "
        "exclude is only for unusable or out-of-scope evidence; "
        "needs_adjudication is only for a genuinely unresolved classification."
    )
    for call, plan in zip(manifest["calls"], plans, strict=True):
        prompt_path = _pin_matches(call["prompt"])
        prompt = prompt_path.read_bytes()
        assert prompt == build_replacement_prompt(plan).encode("utf-8")
        assert call["prompt_utf8_length"] == len(prompt)
        lowered = prompt.decode("utf-8").lower()
        assert all(token not in lowered for token in forbidden)
        assert prompt.decode("utf-8").count(decision_semantics) == 1
        assert plan.host_design_note not in prompt.decode("utf-8")
        assert plan.replacement_id not in prompt.decode("utf-8")
        assert plan.prompt_protocol_version == "v3_decision_semantics"
        assert plan.prior_protocol_diagnostic is not None
        assert plan.prior_protocol_diagnostic.sha256 == DIAGNOSTIC_SHA256


def test_frozen_v4_manifest_and_prompts_match_regeneration(prepared) -> None:
    generated_manifest, _ = prepared
    frozen_manifest_path = FROZEN_REVIEW / "prompt-manifest.coordinator-private.json"
    assert hashlib.sha256(frozen_manifest_path.read_bytes()).hexdigest() == (
        FROZEN_MANIFEST_SHA256
    )
    frozen_manifest = json.loads(frozen_manifest_path.read_text(encoding="utf-8"))
    assert frozen_manifest["freeze_version"] == "v4"
    assert generated_manifest["freeze_version"] == "v4"
    assert frozen_manifest["replacement_order"] == generated_manifest[
        "replacement_order"
    ]
    for frozen_call, generated_call in zip(
        frozen_manifest["calls"], generated_manifest["calls"], strict=True
    ):
        assert frozen_call["replacement_id"] == generated_call["replacement_id"]
        assert frozen_call["replacement_call_id"] == generated_call[
            "replacement_call_id"
        ]
        assert frozen_call["review_item_order"] == generated_call[
            "review_item_order"
        ]
        frozen_prompt = _pin_matches(frozen_call["prompt"]).read_bytes()
        generated_prompt = _pin_matches(generated_call["prompt"]).read_bytes()
        assert frozen_prompt == generated_prompt
        assert frozen_call["prompt_utf8_length"] == len(frozen_prompt)


def test_v2_call01_protocol_diagnostic_is_exact_and_schema_valid() -> None:
    diagnostic_path = REVIEW_V2 / "call-01.protocol-diagnostic.json"
    assert hashlib.sha256(diagnostic_path.read_bytes()).hexdigest() == DIAGNOSTIC_SHA256
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["schema_version"] == "1"
    assert diagnostic["status"] == "rejected_protocol_semantics_ambiguous"
    assert diagnostic["task_identity"] == (
        "/root/config3_transport_resume/replacement_review_01"
    )
    assert diagnostic["review_call_id"] == "rcall-baec252fa9af"
    assert diagnostic["prompt"] == {
        "path": "data/benchmark/t6-v2/replacements/review-v2/prompts/replacement-01.txt",
        "sha256": "aa951b4a31e2f48428b8a7b4829094445e6da3c4a524b62317b5e09dd2a9c996",
    }
    final_bytes = diagnostic["final_message"].encode("utf-8")
    assert hashlib.sha256(final_bytes).hexdigest() == DIAGNOSTIC_FINAL_SHA256
    final = json.loads(final_bytes)
    assert set(final) == {"review_call_id", "sides"}
    assert final["review_call_id"] == diagnostic["review_call_id"]
    assert len(final["sides"]) == 2
    assert all(
        set(side) == {"review_item_id", "review_response"}
        and set(side["review_response"])
        == {
            "decision",
            "drift_type",
            "line_level",
            "rationale",
            "uncertainty_notes",
        }
        for side in final["sides"]
    )
    assert [side["review_item_id"] for side in final["sides"]] == [
        "rvw-24ef9101",
        "rvw-7bb1918d",
    ]
    assert [side["review_response"]["decision"] for side in final["sides"]] == [
        "include",
        "exclude",
    ]
    assert [side["review_response"]["drift_type"] for side in final["sides"]] == [
        "D7_conformant",
        "D5_boundary_error",
    ]
    with pytest.raises(ValidationError, match="excluded items"):
        ReplacementCompletion.model_validate(final)


def test_v3_is_explicitly_superseded_without_launch() -> None:
    marker = REVIEW_V3 / "SUPERSEDED.md"
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == SUPERSEDED_SHA256
    text = marker.read_text(encoding="utf-8")
    assert "superseded by `review-v4`" in text
    assert "No model call was launched from this freeze." in " ".join(text.split())


def test_v4_lineage_and_all_opaque_ids_are_fresh() -> None:
    v2_manifest, v2_plans = _load_review(REVIEW_V2)
    v3_manifest, v3_plans = _load_review(REVIEW_V3)
    v4_manifest, v4_plans = _load_review(FROZEN_REVIEW)

    def call_ids(manifest: dict[str, object]) -> set[str]:
        return {call["replacement_call_id"] for call in manifest["calls"]}

    def review_ids(plans: list[ReplacementPlanItem]) -> set[str]:
        return {side.review_item_id for plan in plans for side in plan.sides}

    def aliases(plans: list[ReplacementPlanItem]) -> set[str]:
        return {side.source_alias for plan in plans for side in plan.sides}

    assert call_ids(v4_manifest).isdisjoint(
        call_ids(v2_manifest) | call_ids(v3_manifest)
    )
    assert review_ids(v4_plans).isdisjoint(review_ids(v2_plans) | review_ids(v3_plans))
    assert aliases(v4_plans).isdisjoint(aliases(v2_plans) | aliases(v3_plans))
    assert v4_plans[0].source.sha256 != v2_plans[0].source.sha256
    assert v4_manifest["prior_protocol_diagnostic"] == {
        "path": "data/benchmark/t6-v2/replacements/review-v2/call-01.protocol-diagnostic.json",
        "sha256": DIAGNOSTIC_SHA256,
    }


def test_private_mapping_is_derived_from_exact_six_rejected_outcomes(prepared) -> None:
    manifest, plans = prepared
    audit_path = _pin_matches(manifest["correction_audit"])
    audit = PairCorrectionAuditManifest.model_validate_json(
        audit_path.read_text(encoding="utf-8")
    )
    assert audit.rejected_nonflip_count == 6
    assert all(item.attempt.outcome == "rejected_nonflip" for item in audit.items)
    assert manifest["replacement_to_rejected_original"].keys() == set(REPLACEMENT_ORDER)
    assert set(manifest["replacement_to_rejected_original"].values()) == set(
        audit.pair_order
    )
    correction_plan_path = ROOT / audit.correction_plan.path
    correction_plans = {
        row.correction_pair_id: row
        for raw in correction_plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
        for row in [PairCorrectionPlanItem.model_validate_json(raw)]
    }
    for plan in plans:
        rejected_id = manifest["replacement_to_rejected_original"][plan.replacement_id]
        assert plan.rejected_pair_id == rejected_id
        assert _authority_signature(plan.sides) == _authority_signature(
            correction_plans[rejected_id].sides
        )


def test_call_identity_and_isolation_contract_is_complete(prepared) -> None:
    manifest, plans = prepared
    assert manifest["model_id"] == "gpt-5.6-luna"
    assert manifest["reasoning_effort"] == "max"
    assert manifest["fork_turns"] == "none"
    assert manifest["tools_authorized"] == 0
    assert manifest["prior_pair_context_included"] is False
    call_ids = [plan.replacement_call_id for plan in plans]
    assert len(call_ids) == len(set(call_ids)) == 6
    assert [call["replacement_call_id"] for call in manifest["calls"]] == call_ids


def test_source_pins_text_programs_calls_and_loci_are_internally_consistent(
    prepared,
) -> None:
    _, plans = prepared
    for plan in plans:
        source_path = _pin_matches(plan.source.model_dump(mode="json"))
        assert source_path.read_text(encoding="utf-8") == plan.shared_source_text
        declared = set(_program_spans(plan.shared_source_text))
        called = {match.upper() for match in CALL_TARGET.findall(plan.shared_source_text)}
        loci = {locus.program.upper() for locus in plan.code_locus.loci}
        assert called <= declared
        assert loci == declared
        for locus in plan.code_locus.loci:
            program_lines = _program_spans(plan.shared_source_text)[
                locus.program.upper()
            ]
            start, end = locus.line_span
            assert start in program_lines and end in program_lines and start <= end
            lines = plan.shared_source_text.splitlines()
            paragraph_lines = [
                index
                for index, line in enumerate(lines, start=1)
                if re.search(rf"\b{re.escape(locus.paragraph)}\.", line)
            ]
            assert any(start <= line <= end for line in paragraph_lines)


def test_review_ids_and_source_aliases_are_opaque_globally_unique(prepared) -> None:
    _, plans = prepared
    review_ids = [side.review_item_id for plan in plans for side in plan.sides]
    aliases = [side.source_alias for plan in plans for side in plan.sides]
    assert len(review_ids) == len(set(review_ids)) == 12
    assert len(aliases) == len(set(aliases)) == 12
    assert all(re.fullmatch(r"rvw-[0-9a-f]{8}", value) for value in review_ids)
    assert all(re.fullmatch(r"src-[0-9a-f]{12}", value) for value in aliases)
    assert not any(
        plan.replacement_id in value
        for plan in plans
        for value in (*review_ids, *aliases)
    )


def test_valid_include_one_d7_one_drift_completion_passes(prepared) -> None:
    _, plans = prepared
    validator = getattr(
        replacement_protocol, "validate_replacement_completion", None
    )
    for plan in plans:
        completion = _valid_completion(plan)
        require_replacement_flip(completion)
        if callable(validator):
            validator(plan, completion)


def test_production_exposes_plan_bound_post_response_validator() -> None:
    _production_plan_validator()


@pytest.mark.parametrize(
    "mutation",
    ("wrong_call", "wrong_id", "wrong_order", "wrong_alias", "wrong_program", "wrong_line"),
)
def test_plan_bound_completion_rejects_identity_and_citation_tampering(
    prepared, mutation: str
) -> None:
    validator = getattr(
        replacement_protocol, "validate_replacement_completion", None
    )
    if not callable(validator):
        pytest.skip("production plan-bound validator is not implemented")
    _, plans = prepared
    plan = plans[0]
    payload = _valid_completion(plan).model_dump(mode="json")
    if mutation == "wrong_call":
        payload["review_call_id"] = "rcall-000000000000"
    elif mutation == "wrong_id":
        payload["sides"][1]["review_item_id"] = "rvw-00000000"
    elif mutation == "wrong_order":
        payload["sides"].reverse()
    elif mutation == "wrong_alias":
        payload["sides"][1]["review_response"]["line_level"][0][
            "source_alias"
        ] = plan.sides[0].source_alias
    elif mutation == "wrong_program":
        payload["sides"][1]["review_response"]["line_level"][0][
            "program"
        ] = "NOTVISIBLE"
    else:
        payload["sides"][1]["review_response"]["line_level"][0]["line"] = 9999
    with pytest.raises(ValueError):
        validator(plan, ReplacementCompletion.model_validate(payload))


def test_nonflip_and_schema_invalid_completions_fail(prepared) -> None:
    _, plans = prepared
    completion = _valid_completion(plans[0])
    payload = completion.model_dump(mode="json")
    payload["sides"][1]["review_response"] = payload["sides"][0]["review_response"]
    with pytest.raises(ValueError, match="temporal flip"):
        require_replacement_flip(ReplacementCompletion.model_validate(payload))
    malformed = completion.model_dump(mode="json")
    del malformed["sides"][0]["review_response"]["rationale"]
    with pytest.raises(ValidationError):
        ReplacementCompletion.model_validate(malformed)
    invalid_response = completion.model_dump(mode="json")["sides"][1][
        "review_response"
    ]
    invalid_response["drift_type"] = "D7_conformant"
    with pytest.raises(ValidationError):
        ReviewResponse.model_validate(invalid_response)


def test_authority_chronology_is_not_fixed_to_alpha_then_beta(prepared) -> None:
    _, plans = prepared
    chronology = [
        plan.sides[0].authority.effective_date
        < plan.sides[1].authority.effective_date
        for plan in plans
    ]
    assert any(chronology)
    assert not all(chronology)
