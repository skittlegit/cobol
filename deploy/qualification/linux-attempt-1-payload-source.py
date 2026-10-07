"""Prepare a distinct Linux offline payload inside a disposable container."""

from __future__ import annotations

import email
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def command(args):
    return subprocess.run(args, check=True)


def prepare(
    input_root=Path("/input"), output=Path("/out"), models_root=Path("/models")
):
    wheelhouse = output / "wheelhouse"
    wheelhouse.mkdir(exist_ok=False)
    project = next(input_root.glob("cobol_archaeologist-*.whl"))
    shutil.copyfile(project, wheelhouse / project.name)
    # DECISION: explicitly stage CPU-only torch, avoiding the PyPI CUDA payload.
    command(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--no-deps",
            "--only-binary=:all:",
            "--index-url",
            "https://download.pytorch.org/whl/cpu",
            "--dest",
            str(wheelhouse),
            "torch==2.13.0+cpu",
        ]
    )
    constraint = output / "cpu-constraint.txt"
    constraint.write_text("torch==2.13.0+cpu\n", encoding="ascii")
    command(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--find-links",
            str(wheelhouse),
            "--constraint",
            str(constraint),
            "--dest",
            str(wheelhouse),
            str(project) + "[models]",
            "setuptools",
        ]
    )
    versions, requirements = {}, []
    for wheel in sorted(wheelhouse.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            name = next(
                n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
            )
            headers = email.message_from_bytes(archive.read(name))
        versions[headers["Name"]] = headers["Version"]
        requirements.append(
            f"{headers['Name']}=={headers['Version']} --hash=sha256:{sha(wheel)}"
        )
    (output / "requirements.txt").write_text(
        "\n".join(sorted(requirements)) + "\n", encoding="utf-8"
    )
    command(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--find-links",
            str(wheelhouse),
            "--require-hashes",
            "-r",
            str(output / "requirements.txt"),
        ]
    )
    shutil.copytree(models_root, output / "models", symlinks=False)
    shutil.copytree(input_root / "assets", output / "assets")
    shutil.copyfile(input_root / "offline.py", output / "offline.py")
    prior = json.loads((input_root / "prior-manifest.json").read_bytes())
    banner = subprocess.check_output(["cobc", "--version"], text=True)
    manifest = {
        "schema_version": "cobol-offline-bundle-v1",
        "profile": "linux-container-distinct-from-windows-standalone",
        "python": {
            "version": platform.python_version(),
            "executable_sha256": sha(sys.executable),
            "platform": platform.platform(),
            "payload": "pinned_container_base",
        },
        "gnucobol": {
            "version_policy": ">=3.1.2,<4",
            "version_of_record": "3.2.0",
            "actual_banner": banner,
            "binary_sha256": sha(shutil.which("cobc")),
            "payload": "pinned_preparer_base_image",
        },
        "grammar": prior["grammar"],
        "dependencies": versions,
        "models": prior["models"],
        "retrieval": "hybrid_rerank",
        "transport": "stdio",
        "corpus_shipped": False,
        "dependency_download_scope": "disposable_Linux_preparation_container_only",
        "torch_profile": "official_CPU_index_2.13.0+cpu",
        "files": [
            {
                "path": p.relative_to(output).as_posix(),
                "version": "sha256-content",
                "sha256": sha(p),
            }
            for p in sorted(output.rglob("*"))
            if p.is_file()
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    sys.path.insert(0, str(output))
    from offline import verify

    verify(output)
    print(
        json.dumps(
            {
                "status": "LINUX_PAYLOAD_VERIFIED",
                "files": len(manifest["files"]),
                "dependencies": len(versions),
            }
        )
    )


if __name__ == "__main__":
    prepare()
