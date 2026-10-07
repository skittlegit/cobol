"""Create anonymous public summaries bound to canonical report bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.release_bundle import ABSOLUTE_HOST_PATH

ROOT = Path(__file__).resolve().parents[1]


def sanitize(value):
    if isinstance(value, dict):
        return {
            k: sanitize(v)
            for k, v in value.items()
            if k not in {"log", "backend", "raw_transcript", "host_events"}
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str) and ABSOLUTE_HOST_PATH.search(value):
        return "host-specific value omitted from public summary"
    return value


def public_markdown(name, raw):
    text = raw.decode()
    if name == "paper.md":
        for old, new in {
            "claim-map.json": "paper-numbers.json",
            "numbers.md": "paper-numbers.json",
            "../LICENSE": "../../LICENSE",
            "../DATASHEET.md": "../../DATASHEET.md",
            "../ANNOTATION.md": "../../ANNOTATION.md",
        }.items():
            text = text.replace(f"]({old})", f"]({new})")
    return text.encode()


def build(root=ROOT):
    root = Path(root).resolve()
    output = root / "release/public"
    output.mkdir(parents=True, exist_ok=True)
    sources = {
        "migration-report.json": "data/migration/report.json",
        "m4-report.json": "data/eval/m4/report.json",
        "detector-decision.json": "data/eval/m4/detector-decision.json",
        "m5-report.json": "data/eval/m5/report.json",
        "paper-numbers.json": "paper/claim-map.json",
    }
    pins = {}
    for name, source in sources.items():
        raw = (root / source).read_bytes()
        data = json.loads(raw)
        if name == "migration-report.json" and data.get("status") != "COMPLETE":
            raise ValueError("public migration report must be terminal")
        checksum = hashlib.sha256(raw).hexdigest()
        body = {
            "schema_version": "public-release-summary-v1",
            "source_sha256": checksum,
            "content": sanitize(data),
        }
        result = (
            json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        ).encode()
        if ABSOLUTE_HOST_PATH.search(result.decode()):
            raise ValueError("public summary retains absolute host path")
        (output / name).write_bytes(result)
        pins[name] = {
            "source": source,
            "source_sha256": checksum,
            "public_sha256": hashlib.sha256(result).hexdigest(),
        }
    for name, source in (
        ("migration-report.md", "data/migration/report.md"),
        ("paper.md", "paper/manuscript.md"),
    ):
        raw = (root / source).read_bytes()
        if ABSOLUTE_HOST_PATH.search(raw.decode()):
            raise ValueError("public Markdown retains absolute host path")
        checksum = hashlib.sha256(raw).hexdigest()
        result = (
            f"schema_version: public-release-summary-v1\nsource_sha256: {checksum}\n\n"
        ).encode() + public_markdown(name, raw)
        (output / name).write_bytes(result)
        pins[name] = {
            "source": source,
            "source_sha256": checksum,
            "public_sha256": hashlib.sha256(result).hexdigest(),
        }
    return {
        "schema_version": "public-release-preparation-receipt-v1",
        "artifacts": pins,
        "submission_state": "governed_by_paper_binding_and_actual_release_receipts",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    print(json.dumps(build(parser.parse_args().root), sort_keys=True, indent=2))
