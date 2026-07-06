"""T0.3 gate: DriftInstance family round-trip and validation (M0 schema freeze)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.schemas import DriftInstance

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "drift_instance_d1_kyc.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


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
    data["code_locus"]["line_span"] = [161, 142]
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
