"""Stage an offline payload solely from locally cached wheels and models."""

from __future__ import annotations

import argparse
import email
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

try:
    from deploy.offline import checksum, verify
except ModuleNotFoundError:
    from offline import checksum, verify

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "embedder": ("BAAI/bge-small-en-v1.5", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"),
    "reranker": (
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "c5ee24cb16019beea0893ab7796b1df96625c6b8",
    ),
    "nli": ("MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli", None),
}


def dependencies():
    todo = [
        "tree-sitter",
        "pydantic",
        "pdfplumber",
        "mcp",
        "sentence-transformers",
        "setuptools",
    ]
    seen = set()
    while todo:
        name = canonicalize_name(todo.pop())
        if name in seen:
            continue
        seen.add(name)
        for raw in metadata.requires(name) or []:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                todo.append(requirement.name)
    return {name: metadata.version(name) for name in sorted(seen)}


def cached_wheels(cache):
    result = {}
    for path in Path(cache).rglob("*.body"):
        try:
            with zipfile.ZipFile(path) as archive:
                met = next(
                    (
                        n
                        for n in archive.namelist()
                        if n.endswith(".dist-info/METADATA")
                    ),
                    None,
                )
                if met is None:
                    continue
                headers = email.message_from_bytes(archive.read(met))
                wheel = email.message_from_bytes(
                    archive.read(met.replace("METADATA", "WHEEL"))
                )
                stem = met.split("/")[0].removesuffix(".dist-info")
                tags = [tag.split("-") for tag in wheel.get_all("Tag")]
                tag = "-".join(
                    ".".join(sorted({row[i] for row in tags})) for i in range(3)
                )
                result[(canonicalize_name(headers["Name"]), headers["Version"])] = (
                    path,
                    f"{stem}-{tag}.whl",
                )
        except (zipfile.BadZipFile, KeyError, OSError):
            continue
    return result


def build(output, *, root=ROOT, pip_cache=None, model_cache=None, nli_cache=None):
    output, root = Path(output).resolve(), Path(root).resolve()
    if output.exists():
        raise ValueError("Bundle target must be a fresh staging directory")
    pip_cache = (
        pip_cache
        or Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
        / "pip/Cache/http-v2"
    )
    cache = cached_wheels(pip_cache)
    versions = dependencies()
    missing = [
        name for name, version in versions.items() if (name, version) not in cache
    ]
    if missing:
        raise ValueError("Missing offline dependency wheels: " + ", ".join(missing))
    output.mkdir(parents=True)
    wheelhouse = output / "wheelhouse"
    wheelhouse.mkdir()
    for name, version in versions.items():
        source, filename = cache[(name, version)]
        shutil.copyfile(source, wheelhouse / filename)
    with tempfile.TemporaryDirectory(prefix="offline-project-wheel-") as staging:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                staging,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        wheel = next(Path(staging).glob("*.whl"))
        shutil.copyfile(wheel, wheelhouse / wheel.name)
    versions["cobol-archaeologist"] = "0.1.0"
    requirements = []
    for wheel in sorted(wheelhouse.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            met = next(
                n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
            )
            headers = email.message_from_bytes(archive.read(met))
        requirements.append(
            f"{headers['Name']}=={headers['Version']} --hash=sha256:{checksum(wheel)}"
        )
    (output / "requirements.txt").write_text(
        "\n".join(sorted(requirements)) + "\n", encoding="utf-8"
    )
    models = {}
    for role, (name, revision) in MODELS.items():
        source_root = (
            Path(nli_cache or Path.home() / ".cache/huggingface/hub")
            if role == "nli"
            else Path(model_cache or root / ".model_cache")
        )
        source = source_root / ("models--" + name.replace("/", "--"))
        if revision is None:
            snapshots = list((source / "snapshots").iterdir())
            if len(snapshots) != 1:
                raise ValueError(
                    "NLI main alias must resolve to exactly one staged snapshot"
                )
            revision = snapshots[0].name
        if len(revision) != 40:
            raise ValueError("Model revision must be an immutable commit hash")
        dest = output / "models" / source.name
        shutil.copytree(
            source / "snapshots" / revision,
            dest / "snapshots" / revision,
            symlinks=False,
        )
        (dest / "refs").mkdir()
        (dest / "refs/main").write_text(revision, encoding="ascii")
        models[role] = {
            "model": name,
            "revision": revision,
            "version": revision,
            "source_revision_alias": "main" if role == "nli" else revision,
        }
    assets = output / "assets"
    assets.mkdir()
    shutil.copyfile(
        root / "tests/fixtures/retrieval/chunks.jsonl", assets / "chunks.jsonl"
    )
    shutil.copyfile(root / "data/regulations/clauses.jsonl", assets / "clauses.jsonl")
    shutil.copyfile(root / "deploy/offline.py", output / "offline.py")
    manifest = {
        "schema_version": "cobol-offline-bundle-v1",
        "python": {
            "version": platform.python_version(),
            "executable_sha256": checksum(Path(sys.executable)),
            "platform": platform.platform(),
            "payload": "external_operator_supplied",
        },
        "gnucobol": {
            "version_policy": ">=3.1.2,<4",
            "version_of_record": "3.2.0",
            "payload": "optional_external_operator_supplied",
        },
        "grammar": {"revision": "e99dbdc3d800d5fa2796476efd60af91f6b43d93"},
        "dependencies": versions,
        "models": models,
        "retrieval": "hybrid_rerank",
        "transport": "stdio",
        "corpus_shipped": False,
        "files": [
            {
                "path": p.relative_to(output).as_posix(),
                "version": "0.1.0" if p.name == "offline.py" else "sha256-content",
                "sha256": checksum(p),
            }
            for p in sorted(output.rglob("*"))
            if p.is_file()
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    verify(output)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output)
    print(
        json.dumps(
            {
                "files": len(result["files"]),
                "dependencies": len(result["dependencies"]),
                "status": "STAGED",
            }
        )
    )
