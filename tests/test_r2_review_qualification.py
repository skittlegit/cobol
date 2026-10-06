"""Qualification preparation retains exact existing evidence on resume."""

import importlib.util
from pathlib import Path

import pytest


def module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts/prepare_r2_review_qualification.py"
    )
    spec = importlib.util.spec_from_file_location("review_qualification", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_immutable_qualification_bytes_cannot_be_replaced(tmp_path):
    builder = module()
    builder.OUT = tmp_path
    builder.save("packet.txt", b"original")
    with pytest.raises(ValueError, match="immutable"):
        builder.save("packet.txt", b"changed")
    assert (tmp_path / "packet.txt").read_bytes() == b"original"


def test_existing_qualification_rechecks_evidence_without_new_call(tmp_path):
    builder = module()
    builder.OUT = tmp_path
    request = builder.prepare()
    assert builder.prepare() == request
    (tmp_path / request.prompt.path).write_bytes(b"changed packet")
    with pytest.raises(ValueError, match="input changed"):
        builder.prepare()
