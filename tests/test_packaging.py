"""Cross-track packaging and infrastructure regression gates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_declares_runtime_assets():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    setup = (REPO_ROOT / "setup.py").read_text(encoding="utf-8")
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert '"build"' in pyproject
    assert '"vendor" / "tree-sitter-cobol"' in setup
    assert '"data" / "regulations" / "sources"' in setup
    assert "recursive-include vendor/tree-sitter-cobol" in manifest
    assert "recursive-include data/regulations/sources" in manifest


def test_built_wheel_resolves_assets_outside_checkout(tmp_path):
    dist_dir = tmp_path / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(dist_dir),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist_dir.glob("*.whl"))
    sdist = next(dist_dir.glob("*.tar.gz"))
    with tarfile.open(sdist) as archive:
        sdist_names = archive.getnames()
    assert any(
        name.endswith("vendor/tree-sitter-cobol/src/parser.c") for name in sdist_names
    )
    assert any(
        name.endswith("data/regulations/sources/MANIFEST.json") for name in sdist_names
    )
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert "cobol_archaeologist/_assets/tree-sitter-cobol/src/parser.c" in names
    assert "cobol_archaeologist/_assets/regulations/sources/MANIFEST.json" in names
    assert "cobol_archaeologist/_assets/regulations/clauses.jsonl" in names

    target = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    probe_dir = tmp_path / "outside-checkout"
    probe_dir.mkdir()
    code = """
import json
from cobol_archaeologist.parser import _grammar
from cobol_archaeologist.rag import chunker
print(json.dumps({
    "grammar": (
        (_grammar._VENDOR_DIR / "src" / "parser.c").is_file()
        and _grammar.get_language() is not None
    ),
    "manifest": chunker.MANIFEST.is_file(),
    "clauses": chunker.CLAUSES.is_file(),
}))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(target)
    probe = subprocess.run(
        [sys.executable, "-c", code],
        cwd=probe_dir,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(probe.stdout) == {
        "grammar": True,
        "manifest": True,
        "clauses": True,
    }


def test_ci_workflow_runs_offline_quality_gates():
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "pull_request:" in text and "master" in text
    assert "actions/checkout@v7" in text
    assert "fetch-depth: 0" in text
    assert "actions/setup-python@v6" in text
    assert "python -m ruff check" in text
    assert "python -m pytest" in text
