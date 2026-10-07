"""Offline deployment integrity gates; live qualification is a separate receipt."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from deploy import offline
from deploy.build_bundle import cached_wheels


@pytest.fixture
def bundle(tmp_path):
    models = {}
    for role in ("embedder", "reranker", "nli"):
        model = {"model": "test/" + role, "revision": "a" * 40}
        models[role] = model
        path = (
            tmp_path
            / f"models/models--test--{role}/snapshots/{model['revision']}/model.safetensors"
        )
        path.parent.mkdir(parents=True)
        path.write_bytes(b"unit test integrity payload only; not neural qualification")
    (tmp_path / "requirements.txt").write_text("offline-unit-fixture", encoding="ascii")
    manifest = {
        "schema_version": "cobol-offline-bundle",
        "models": models,
        "files": [
            {"path": p.relative_to(tmp_path).as_posix(), "sha256": offline.checksum(p)}
            for p in tmp_path.rglob("*")
            if p.is_file()
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_verified_files_and_exact_manifest(bundle):
    assert offline.verify(bundle)["schema_version"] == "cobol-offline-bundle"


@pytest.mark.parametrize(
    "failure", ["missing", "checksum", "extra", "duplicate", "escape", "uncached"]
)
def test_refuses_bad_bundle(bundle, failure):
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if failure == "missing":
        (bundle / manifest["files"][0]["path"]).unlink()
    elif failure == "checksum":
        (bundle / manifest["files"][0]["path"]).write_bytes(b"changed")
    elif failure == "extra":
        (bundle / "secret.txt").write_bytes(b"unexpected")
    elif failure == "duplicate":
        manifest["files"].append(manifest["files"][0])
    elif failure == "escape":
        manifest["files"][0]["path"] = "../outside-payload"
    else:
        manifest["models"]["embedder"]["revision"] = "b" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        offline.verify(bundle)


def test_missing_corpus_stops_before_model_loading(bundle):
    with pytest.raises(ValueError, match="Missing corpus"):
        offline.serve(bundle, bundle / "absent")


def test_network_guard_rejects_actual_socket_and_dns():
    code = "from deploy.offline import disable_network; import socket; disable_network(); socket.getaddrinfo('example.com',443)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert (
        result.returncode != 0
        and "Offline deployment refuses network access" in result.stderr
    )
    code = "from deploy.offline import disable_network; import socket; disable_network(); socket.socket().connect(('8.8.8.8',443))"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert (
        result.returncode != 0
        and "Offline deployment refuses network access" in result.stderr
    )


def test_container_recipe_and_allowlist():
    root = Path(__file__).resolve().parents[1]
    recipe = (root / "deploy/Dockerfile").read_text()
    assert "USER 65532:65532" in recipe
    assert "apt-get" not in recipe and "pip download" not in recipe
    assert "COPY bundle/" in recipe and "COPY ." not in recipe
    assert "--corpus" in recipe
    assert (root / "deploy/.dockerignore").read_text().startswith("*\n")


def test_cached_multi_python_tags_preserved(tmp_path):
    path = tmp_path / "cache.body"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("demo-1.0.dist-info/METADATA", "Name: demo\nVersion: 1.0\n")
        archive.writestr(
            "demo-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nTag: py2-none-any\nTag: py3-none-any\n",
        )
    assert (
        cached_wheels(tmp_path)[("demo", "1.0")][1] == "demo-1.0-py2.py3-none-any.whl"
    )


def test_guard_allows_private_windows_socketpair():
    code = "from deploy.offline import disable_network; import socket; disable_network(); a,b=socket.socketpair(); a.close(); b.close()"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
