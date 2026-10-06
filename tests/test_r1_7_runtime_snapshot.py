from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/snapshot_r1_7_runtime.py"
spec = importlib.util.spec_from_file_location("r17_snapshot", SCRIPT)
assert spec is not None and spec.loader is not None
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def test_runtime_archive_roundtrip_and_existing_snapshot_tamper(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/method.py").write_bytes(b"method = 1\r\n")
    (tmp_path / "pyproject.toml").write_bytes(b"[project]\r\n")
    out = tmp_path / "data/eval/m4/gpt6-luna-repeat/diagnostics"
    out.mkdir(parents=True)
    expected = snapshot.runtime_source_sha256(tmp_path)
    (out / "r1.6-terminal-receipt.json").write_text(
        json.dumps({"runtime_source_sha256": expected}), encoding="utf-8")
    receipt = snapshot.snapshot(tmp_path)
    snapshot.snapshot(tmp_path)
    with ZipFile(tmp_path / receipt["archive_path"]) as archive:
        assert archive.read("src/method.py") == b"method = 1\r\n"
    (tmp_path / "src/method.py").write_bytes(b"method = 2\r\n")
    with pytest.raises(ValueError, match="source runtime differs"):
        snapshot.snapshot(tmp_path)


def test_completed_runtime_cannot_be_snapshotted_under_wrong_identity(tmp_path):
    (tmp_path / "pyproject.toml").write_bytes(b"[project]\n")
    out = tmp_path / "data/eval/m4/gpt6-luna-repeat/diagnostics"
    out.mkdir(parents=True)
    (out / "r1.6-terminal-receipt.json").write_text(
        json.dumps({"runtime_source_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(ValueError, match="source runtime differs"):
        snapshot.snapshot(tmp_path)
