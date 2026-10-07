from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_bundle", ROOT / "scripts/release_bundle.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def command(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    )


@pytest.fixture
def clean_repo(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    for name in release.FIXED_PATHS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == "RELEASE.md":
            target.write_text("Test-only release fixture: NOT_EVALUABLE; NO_GO.\n")
        else:
            shutil.copyfile(ROOT / name, target)
    for source in (ROOT / "src/cobol_archaeologist").rglob("*.py"):
        target = root / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    command(root, "init")
    command(root, "config", "core.autocrlf", "false")
    command(root, "config", "user.name", "Release Test")
    command(root, "config", "user.email", "release-test@example.invalid")
    command(root, "add", ".")
    command(root, "commit", "-m", "clean release fixture")
    return root


def test_real_benchmark_counts_and_locked_schema_validation():
    assert release.validate_benchmark(ROOT)["historical_t6_pairs"] == 9


def test_two_clean_archives_and_outside_tree_verification(clean_repo, tmp_path):
    first, second = tmp_path / "one.zip", tmp_path / "two.zip"
    receipt = release.two_clean_builds(clean_repo, first, second)
    assert receipt["status"] == "IDENTICAL"
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(first) as archive:
        assert not any(
            "model_cache" in name or name.endswith(".pdf")
            for name in archive.namelist()
        )
        archive.extractall(unpacked)
    assert release.verify_unpacked(unpacked)["status"] == "VALID"
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    replay = subprocess.run(
        [
            sys.executable,
            "-B",
            str(unpacked / "scripts/build_release.py"),
            "verify",
            "--root",
            str(unpacked),
        ],
        cwd=unpacked,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(replay.stdout)["status"] == "VALID"
    (unpacked / "unexpected.json").write_text("{}")
    with pytest.raises(ValueError, match="unexpected"):
        release.verify_unpacked(unpacked)


@pytest.mark.parametrize("kind", ["tracked", "untracked"])
def test_dirty_git_identity_refused(clean_repo, tmp_path, kind):
    path = clean_repo / ("README.md" if kind == "tracked" else "secret-token.txt")
    path.write_text("dirty")
    with pytest.raises(ValueError, match="clean"):
        release.build(clean_repo, tmp_path / "bad.zip")


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("count", "stale"),
        ("hash", "checksum"),
        ("missing", "missing"),
        ("annotation", "locked annotation"),
    ],
)
def test_committed_corrupt_inputs_are_rejected(clean_repo, tmp_path, mutation, match):
    manifest_path = clean_repo / "data/benchmark/v1/manifest.json"
    if mutation == "count":
        data = json.loads(manifest_path.read_bytes())
        data["split_counts"]["test"] = 195
        manifest_path.write_text(json.dumps(data))
    elif mutation == "hash":
        with (clean_repo / "data/benchmark/v1/train.jsonl").open("ab") as stream:
            stream.write(b"\n")
    elif mutation == "annotation":
        with (clean_repo / "data/benchmark/annotation/pass_1_Human-Primary.jsonl").open(
            "ab"
        ) as stream:
            stream.write(b"\n")
    else:
        (clean_repo / "data/benchmark/annotation/adjudication_log.jsonl").unlink()
    command(clean_repo, "add", "-A")
    command(clean_repo, "commit", "-m", "invalid frozen input")
    with pytest.raises(ValueError, match=match):
        release.build(clean_repo, tmp_path / "bad.zip")


def test_unpacked_size_hash_license_corruption(clean_repo, tmp_path):
    output = tmp_path / "release.zip"
    release.build(clean_repo, output)
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(unpacked)
    manifest_path = unpacked / "release/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"][0]["license"] = "invented"
    manifest_path.write_bytes(release.json_bytes(manifest))
    with pytest.raises(ValueError, match="license mismatch"):
        release.verify_unpacked(unpacked)


def test_safe_path_traversal_refused(tmp_path):
    with pytest.raises(ValueError, match="unsafe"):
        release.safe_file(tmp_path, "../secret")


def test_outputs_must_be_outside_tree(clean_repo):
    with pytest.raises(ValueError, match="outside"):
        release.build(clean_repo, clean_repo / "release.zip")


def public_summary_fixture(root):
    for name in release.PUBLIC_SUMMARIES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".json"):
            path.write_bytes(
                release.json_bytes(
                    {
                        "schema_version": "public-release-summary-v1",
                        "source_sha256": "a" * 64,
                        "content": {"decision": "NOT_EVALUABLE"},
                    }
                )
            )
        else:
            path.write_text(
                "schema_version: public-release-summary-v1\nsource_sha256: "
                + "a" * 64
                + "\nPublic summary.\n"
            )


def test_successor_summary_schema_and_absolute_path_rejection(tmp_path):
    public_summary_fixture(tmp_path)
    release.validate_public_summaries(tmp_path)
    path = tmp_path / release.PUBLIC_SUMMARIES[0]
    data = json.loads(path.read_bytes())
    data["content"]["compiler"] = "C:/Users/private/compiler.exe"
    path.write_bytes(release.json_bytes(data))
    with pytest.raises(ValueError, match="absolute host path"):
        release.validate_public_summaries(tmp_path)
    data["content"].pop("compiler")
    data["source_sha256"] = "not-a-hash"
    path.write_bytes(release.json_bytes(data))
    with pytest.raises(ValueError, match="schema/source pin"):
        release.validate_public_summaries(tmp_path)


def test_successor_profile_requires_public_terminal_summaries(clean_repo, tmp_path):
    with pytest.raises(ValueError, match="missing"):
        release.build(clean_repo, tmp_path / "successor.zip", profile="successor")
    public_summary_fixture(clean_repo)
    command(clean_repo, "add", ".")
    command(clean_repo, "commit", "-m", "public test-only successor summaries")
    output = tmp_path / "successor.zip"
    result = release.build(clean_repo, output, profile="successor")
    assert result["manifest"]["profile"] == "successor"
    with zipfile.ZipFile(output) as archive:
        assert set(release.PUBLIC_SUMMARIES).issubset(archive.namelist())


def test_builder_rejects_unexpected_benchmark_file(tmp_path):
    directory = tmp_path / "data/benchmark/v1"
    directory.mkdir(parents=True)
    for name in [
        "manifest.json",
        "train.jsonl",
        "dev.jsonl",
        "test.jsonl",
        "unexpected.json",
    ]:
        (directory / name).write_text("{}")
    with pytest.raises(ValueError, match="unexpected"):
        release.validate_benchmark(tmp_path)


def test_regulation_clauses_are_typed_unique_and_external_source_licensed(tmp_path):
    source = ROOT / "data/regulations/clauses.jsonl"
    rows = [
        json.loads(line) for line in source.read_bytes().splitlines() if line.strip()
    ]
    destination = tmp_path / "data/regulations/clauses.jsonl"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(source.read_bytes())
    assert release.validate_regulation_clauses(tmp_path) == 21
    metadata = release.file_metadata(
        "data/regulations/clauses.jsonl", source.read_bytes()
    )
    assert metadata["role"] == "quoted-regulation-clauses"
    assert metadata["license"].startswith("external-RBI-source-terms;")
    assert "no MIT redistribution grant" in metadata["license"]
    destination.write_text("\n".join(json.dumps(row) for row in [*rows, rows[0]]))
    with pytest.raises(ValueError, match="unique"):
        release.validate_regulation_clauses(tmp_path)
    rows[0]["clause"].pop("effective_date")
    destination.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match="effective_date"):
        release.validate_regulation_clauses(tmp_path)


def test_actual_unpacked_archive_builds_wheel_without_corpora_or_pdf_payloads(
    clean_repo,
):
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cobol-release-wheel-") as temporary:
        outside = Path(temporary)
        assert outside.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert not outside.resolve().is_relative_to(ROOT.resolve())
        archive_path = outside / "release.zip"
        release.build(clean_repo, archive_path)
        unpacked = outside / "unpacked"
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(unpacked)
        assert not list(unpacked.rglob("*.pdf"))
        assert not (unpacked / "data/corpora").exists()
        assert release.verify_unpacked(unpacked)["status"] == "VALID"
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.update(
            {"PIP_NO_INDEX": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        )
        output = outside / "dist"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--wheel",
                "--outdir",
                str(output),
            ],
            cwd=unpacked,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        wheel = next(output.glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            assert (
                archive.read(
                    "cobol_archaeologist/_assets/tree-sitter-cobol/src/parser.c"
                )
                == (ROOT / "vendor/tree-sitter-cobol/src/parser.c").read_bytes()
            )
            assert (
                archive.read("cobol_archaeologist/_assets/regulations/clauses.jsonl")
                == (ROOT / "data/regulations/clauses.jsonl").read_bytes()
            )
            assert (
                archive.read(
                    "cobol_archaeologist/_assets/regulations/sources/MANIFEST.json"
                )
                == (ROOT / "data/regulations/sources/MANIFEST.json").read_bytes()
            )
            assert not any(name.endswith(".pdf") for name in archive.namelist())
