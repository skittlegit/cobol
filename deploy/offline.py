"""Verified, network-disabled stdio deployment of the unchanged tool stack."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(bundle):
    bundle = Path(bundle).resolve()
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    if manifest["schema_version"] != "cobol-offline-bundle-v1":
        raise ValueError("Unsupported offline bundle manifest")
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Use the recorded Python 3.12 runtime")
    files = manifest["files"]
    if len({f["path"] for f in files}) != len(files):
        raise ValueError("Duplicate payload path")
    for item in files:
        path = bundle / item["path"]
        if not path.resolve().is_relative_to(bundle) or any(
            p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(bundle)
        ):
            raise ValueError("Unsafe or symlink payload path")
        if not path.is_file():
            raise ValueError(
                f"Missing required local payload: {item['path']}; restage the verified bundle"
            )
        if checksum(path) != item["sha256"]:
            raise ValueError(
                f"Checksum mismatch: {item['path']}; restage the verified bundle"
            )
    observed = {
        p.relative_to(bundle).as_posix()
        for p in bundle.rglob("*")
        if p.is_file() and p.relative_to(bundle).as_posix() != "manifest.json"
    }
    if observed != {f["path"] for f in files}:
        raise ValueError("Unexpected or unmanifested bundle payload")
    for name in ("embedder", "reranker", "nli"):
        model = manifest["models"][name]
        prefix = f"models/models--{model['model'].replace('/', '--')}/snapshots/{model['revision']}/"
        if not any(
            f["path"].startswith(prefix)
            and f["path"].endswith((".safetensors", ".bin"))
            for f in files
        ):
            raise ValueError(
                f"Missing uncached requested model: {name}; stage the exact model revision"
            )
    return manifest


def disable_network():
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PIP_NO_INDEX"] = "1"

    def audit(event, args):
        if event in {
            "socket.connect",
            "socket.connect_ex",
            "socket.bind",
            "socket.getaddrinfo",
        }:
            address = args[0] if event == "socket.getaddrinfo" else args[1]
            host = address[0] if isinstance(address, tuple) else address
            try:
                loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = False
            # DECISION: Windows asyncio's private socketpair uses loopback.
            # Reject external network, while retaining stdio event-loop support.
            if not loopback:
                raise PermissionError("Offline deployment refuses network access")

    sys.addaudithook(audit)


def serve(bundle, corpus, copybooks=(), *, retrieval="hybrid_rerank"):
    bundle, corpus = Path(bundle).resolve(), Path(corpus).resolve()
    verify(bundle)
    if not corpus.is_dir() or not any(corpus.rglob("*.cbl")):
        raise ValueError(
            "Missing corpus: mount a directory containing COBOL source files"
        )
    if any(not Path(p).is_dir() for p in copybooks):
        raise ValueError("Missing copybook directory: mount every configured COPY path")
    disable_network()
    os.environ["COBOL_MODEL_CACHE"] = str(bundle / "models")
    os.environ["HF_HOME"] = str(bundle / "models")
    os.environ["HF_HUB_CACHE"] = str(bundle / "models")
    from cobol_archaeologist.mcp_server.server import build_server
    from cobol_archaeologist.rag.search import RegulationSearch
    from cobol_archaeologist.tools import RealToolLayer

    layer = RealToolLayer(
        corpus_root=corpus, copybook_paths=[Path(p) for p in copybooks]
    )
    # DECISION: packaged deployment selects explicit bundled regulation paths;
    # the frozen package's checkout-relative defaults are never rewritten.
    layer._reg_search = RegulationSearch(
        chunks_path=bundle / "assets/chunks.jsonl",
        clauses_path=bundle / "assets/clauses.jsonl",
        mode=retrieval,
    )
    build_server(layer).run(transport="stdio")


def install(bundle, environment):
    bundle = Path(bundle).resolve()
    verify(bundle)
    environment = Path(environment).resolve()
    if environment.exists():
        raise ValueError("Installation target must be a new clean directory")
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--find-links",
            str(bundle / "wheelhouse"),
            "--require-hashes",
            "-r",
            str(bundle / "requirements.txt"),
        ],
        check=True,
        env={**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    return python


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("verify", "install", "serve"))
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--environment", type=Path)
    p.add_argument("--corpus", type=Path)
    p.add_argument("--copybook", type=Path, action="append", default=[])
    p.add_argument(
        "--retrieval", choices=("bm25", "hybrid_rerank"), default="hybrid_rerank"
    )
    a = p.parse_args()
    if a.action == "verify":
        verify(a.bundle)
        print(json.dumps({"status": "VERIFIED", "python": platform.python_version()}))
    elif a.action == "install":
        if a.environment is None:
            p.error("--environment is required")
        print(install(a.bundle, a.environment))
    else:
        if a.corpus is None:
            p.error("--corpus is required")
        serve(a.bundle, a.corpus, a.copybook, retrieval=a.retrieval)


if __name__ == "__main__":
    main()
