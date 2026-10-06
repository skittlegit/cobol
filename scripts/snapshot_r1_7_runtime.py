"""Preserve the completed evaluator's exact runtime before successor work."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from cobol_archaeologist.eval.config4_prepare import runtime_source_sha256

ROOT = Path(__file__).resolve().parents[1]


def snapshot(root: Path = ROOT) -> dict:
    out = root / "data/eval/m4"
    terminal = json.loads((out / "gpt6-luna-repeat/diagnostics/r1.6-terminal-receipt.json").read_text(encoding="utf-8"))
    expected = terminal["runtime_source_sha256"]
    if runtime_source_sha256(root) != expected:
        raise ValueError("source runtime differs from completed evaluation")
    paths = [root / "pyproject.toml", *sorted((root / "src").rglob("*.py"))]
    paths += sorted(p for p in (root / "vendor/tree-sitter-cobol").rglob("*") if p.is_file())
    target = out / "runtime-source.zip"
    pins = {}
    if target.exists():
        with ZipFile(target) as archive:
            for path in paths:
                relative = path.relative_to(root).as_posix()
                payload = path.read_bytes()
                if archive.read(relative) != payload:
                    raise ValueError(f"existing snapshot differs: {relative}")
                pins[relative] = hashlib.sha256(payload).hexdigest()
    else:
        with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for path in paths:
                relative = path.relative_to(root).as_posix()
                payload = path.read_bytes()
                info = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload)
                pins[relative] = hashlib.sha256(payload).hexdigest()
    receipt = {"schema_version": "completed-evaluator-runtime-snapshot-v1",
               "runtime_source_sha256": expected,
               "archive_path": "data/eval/m4/runtime-source.zip",
               "archive_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
               "files": pins, "provider_calls": 0,
               "purpose": "Exact evaluation runtime preserved before additive R2 development; ZIP metadata deterministic and every original file byte retained."}
    payload = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    manifest = out / "runtime-source-manifest.json"
    if manifest.exists() and manifest.read_bytes() != payload:
        raise ValueError("existing runtime snapshot receipt differs")
    manifest.write_bytes(payload)
    print(json.dumps({"runtime_source_sha256": expected, "files": len(pins), "archive_bytes": target.stat().st_size}))
    return receipt


if __name__ == "__main__":
    snapshot()
