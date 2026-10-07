"""Real validation cannot silently substitute fixtures or repeat terminal work."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.validate_r2_stage_generation import (
    check_backend,
    load_fixtures,
    read_terminal,
)


def fixture_tree(tmp_path):
    source = {"path": "DEMO.cbl", "sha256": "a" * 64}
    body = {
        "schema_version": "migration-execution-fixtures-v1",
        "case_id": "migration_demo",
        "frozen_sources": [source],
        "checks": {},
        "fixture_authoring_evidence_sha256": "b" * 64,
    }
    raw = json.dumps(body).encode()
    (tmp_path / "fixtures.json").write_bytes(raw)
    case = SimpleNamespace(
        case_id="migration_demo",
        frozen_sources=[
            SimpleNamespace(model_dump=lambda frozen=dict(source), **kwargs: frozen)
        ],
        fixture_evidence=[
            SimpleNamespace(
                path="fixtures.json", sha256=hashlib.sha256(raw).hexdigest()
            )
        ],
    )
    return case, body


def test_fixture_pin_and_case_binding(tmp_path):
    case, _ = fixture_tree(tmp_path)
    assert load_fixtures(case, tmp_path).case_id == case.case_id
    (tmp_path / "fixtures.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        load_fixtures(case, tmp_path)


def test_fixture_source_binding(tmp_path):
    case, body = fixture_tree(tmp_path)
    body["frozen_sources"][0]["sha256"] = "c" * 64
    raw = json.dumps(body).encode()
    (tmp_path / "fixtures.json").write_bytes(raw)
    case.fixture_evidence[0].sha256 = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="source"):
        load_fixtures(case, tmp_path)


def test_exactly_one_fixture_protocol(tmp_path):
    case, _ = fixture_tree(tmp_path)
    case.fixture_evidence *= 2
    with pytest.raises(ValueError, match="exactly one"):
        load_fixtures(case, tmp_path)


def test_terminal_validation_not_repeated(tmp_path):
    path = tmp_path / "validation.json"
    assert read_terminal(path, "key", "official") is None
    path.write_text(
        json.dumps({"run_key": "key", "execution_purpose": "qualification"})
    )
    with pytest.raises(ValueError, match="purpose"):
        read_terminal(path, "key", "official")
    path.write_text(json.dumps({"run_key": "other", "execution_purpose": "official"}))
    with pytest.raises(ValueError, match="identity"):
        read_terminal(path, "key", "official")


def test_qualified_backend_identity_must_match(tmp_path):
    body = {
        "backend": {
            "compiler": {"binary_sha256": "a" * 64},
            "backend_identity_sha256": "b" * 64,
        }
    }
    raw = json.dumps(body).encode()
    (tmp_path / "qualified-capability.json").write_bytes(raw)
    case = SimpleNamespace(
        fixture_evidence=[
            SimpleNamespace(
                path="qualified-capability.json", sha256=hashlib.sha256(raw).hexdigest()
            )
        ]
    )
    assert check_backend(case, tmp_path, body["backend"]) == body["backend"]
    with pytest.raises(ValueError, match="qualified backend"):
        check_backend(
            case,
            tmp_path,
            {
                "compiler": {"binary_sha256": "c" * 64},
                "backend_identity_sha256": "b" * 64,
            },
        )
