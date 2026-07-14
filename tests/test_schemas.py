"""T0.3a gate: DriftInstance family v2 round-trip and validation (schema re-freeze).

All seven v1 gates are preserved (retargeted to the v2 fixture shape); gates
8–16 cover the v2 additions: recursive typed CurrentValue + comparator,
loci/SourceLineRef, resolve_path, the interprocedural one-way validator,
line/locus integrity, and target_path.
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.schemas import CurrentValue, DriftInstance, resolve_path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE = FIXTURES / "drift_instance_d1_kyc.json"
INTERPROC_FIXTURE = FIXTURES / "drift_instance_d3x_interproc.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# A 3-leaf composite mirroring CC-08a (closure window / penalty / day basis).
COMPOSITE_CC08A = {
    "kind": "composite",
    "value": {
        "closure_window": {
            "kind": "duration_working_days",
            "value": 7,
            "comparator": "at_most",
        },
        "penalty_per_day": {
            "kind": "amount_inr",
            "value": 500,
            "comparator": "at_least",
        },
        "day_basis": {"kind": "enum_set", "value": ["calendar_day"]},
    },
}


def composite_d1_data() -> dict:
    """The d1 fixture retargeted at a composite clause with a leaf target_path."""
    data = load_fixture()
    data["regulation_clause"]["current_value"] = copy.deepcopy(COMPOSITE_CC08A)
    data["target_path"] = "penalty_per_day"
    return data


# --- v1 gates (preserved, retargeted to v2) ------------------------------------


def test_round_trip():
    first = DriftInstance.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    second = DriftInstance.model_validate_json(first.model_dump_json())
    assert second == first


def test_effective_date_required():
    data = load_fixture()
    del data["regulation_clause"]["effective_date"]
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_version_required():
    data = load_fixture()
    del data["regulation_clause"]["version"]
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_drift_type_literal_enforced():
    data = load_fixture()
    data["drift_type"] = "D8_bogus"
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_d7_with_drift_labels_rejected():
    data = load_fixture()
    data["drift_type"] = "D7_conformant"
    assert data["labels"]["program_level"] == "drift"
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_d1_with_conformant_program_label_rejected():
    data = load_fixture()
    data["labels"]["program_level"] = "conformant"
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_line_span_must_be_ordered():
    data = load_fixture()
    data["code_locus"]["loci"][0]["line_span"] = [161, 142]
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_extra_fields_forbidden():
    data = load_fixture()
    data["unexpected_key"] = "nope"
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_synthetic_drift_requires_mutation():
    data = load_fixture()
    data["provenance"]["mutation"] = None
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


# --- Gate 8: recursive CurrentValue round-trips --------------------------------


def test_composite_current_value_round_trips():
    cv = CurrentValue.model_validate(COMPOSITE_CC08A)
    again = CurrentValue.model_validate_json(cv.model_dump_json())
    assert again == cv
    assert isinstance(again.value, dict) and len(again.value) == 3


# --- Gate 9: composite discipline ----------------------------------------------


def test_composite_with_scalar_value_rejected():
    with pytest.raises(ValidationError):
        CurrentValue.model_validate({"kind": "composite", "value": 7})


def test_composite_carrying_comparator_rejected():
    with pytest.raises(ValidationError):
        CurrentValue.model_validate(
            {
                "kind": "composite",
                "comparator": "at_most",
                "value": {"a": {"kind": "amount_inr", "value": 1}},
            }
        )


def test_non_composite_with_mapping_value_rejected():
    with pytest.raises(ValidationError):
        CurrentValue.model_validate(
            {"kind": "amount_inr", "value": {"a": {"kind": "amount_inr", "value": 1}}}
        )


# --- Gate 10: comparator literal -----------------------------------------------


def test_unknown_comparator_rejected():
    with pytest.raises(ValidationError):
        CurrentValue.model_validate(
            {"kind": "amount_inr", "value": 500, "comparator": "greater_than"}
        )


# --- Gate 11: resolve_path -----------------------------------------------------


def test_resolve_path_resolves_and_raises():
    cv = CurrentValue.model_validate(COMPOSITE_CC08A)
    leaf = resolve_path(cv, "penalty_per_day")
    assert leaf.kind == "amount_inr" and leaf.value == 500
    with pytest.raises(KeyError):
        resolve_path(cv, "no_such_key")


# --- Gate 12: bool/int union does not coerce -----------------------------------


def test_bool_value_stays_bool():
    cv = CurrentValue.model_validate({"kind": "flag", "value": True})
    # The load-bearing assertion: it is a real bool, not coerced to 1.
    assert cv.value is True and type(cv.value) is bool
    again = CurrentValue.model_validate_json(cv.model_dump_json())
    assert type(again.value) is bool and again.value is True


# --- Gate 13: interprocedural one-way validator --------------------------------


def test_two_program_loci_require_interprocedural_true():
    data = load_fixture()
    data["code_locus"]["loci"].append(
        {
            "program": "OTHER.cbl",
            "paragraph": "9000-X",
            "file": None,
            "line_span": [10, 20],
        }
    )
    data["code_locus"]["is_interprocedural"] = False
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_single_program_may_be_interprocedural():
    # Cross-paragraph single-program case (playbook §1E) — is_interprocedural
    # True with one program is legitimate.
    data = load_fixture()
    data["code_locus"]["is_interprocedural"] = True
    DriftInstance.model_validate(data)  # must not raise


# --- Gate 14: line/locus integrity ---------------------------------------------


def test_line_ref_outside_span_rejected():
    data = load_fixture()
    data["labels"]["line_level"] = [
        {"program": "KYCUPD.cbl", "line": 999, "file": None}
    ]
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_line_ref_program_matching_no_locus_rejected():
    data = load_fixture()
    data["labels"]["line_level"] = [
        {"program": "NOPE.cbl", "line": 147, "file": None}
    ]
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


# --- Gate 15: target_path ------------------------------------------------------


def test_composite_d1_without_target_path_rejected():
    data = composite_d1_data()
    data["target_path"] = None
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_target_path_to_composite_node_rejected():
    data = composite_d1_data()
    # Nest the composite one level so a path can land on a composite node.
    data["regulation_clause"]["current_value"] = {
        "kind": "composite",
        "value": {"charges": copy.deepcopy(COMPOSITE_CC08A)},
    }
    data["target_path"] = "charges"
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


def test_valid_composite_d1_with_leaf_target_path():
    DriftInstance.model_validate(composite_d1_data())  # must not raise


def test_target_path_without_current_value_rejected():
    data = load_fixture()
    data["regulation_clause"]["current_value"] = None
    data["target_path"] = "penalty_per_day"
    with pytest.raises(ValidationError):
        DriftInstance.model_validate(data)


# --- Gate 16: interprocedural fixture ------------------------------------------


def test_interproc_fixture_round_trips():
    first = DriftInstance.model_validate_json(
        INTERPROC_FIXTURE.read_text(encoding="utf-8")
    )
    second = DriftInstance.model_validate_json(first.model_dump_json())
    assert second == first
    assert first.code_locus.is_interprocedural is True
    assert len({loc.program for loc in first.code_locus.loci}) == 2
    assert any(loc.file == "CVACT03Y" for loc in first.code_locus.loci)
