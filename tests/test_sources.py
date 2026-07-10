"""T2.5 Phase 1 gate: every pinned source PDF matches its sha256 in MANIFEST.json.

`skipif` the sources archive is absent so CI without the (large, manually
downloaded) PDFs stays green; the T2.5 gate run itself requires them present.
"""

import hashlib
import json
from pathlib import Path

import pytest

SOURCES = Path(__file__).resolve().parents[1] / "data" / "regulations" / "sources"
MANIFEST = SOURCES / "MANIFEST.json"

pytestmark = pytest.mark.skipif(
    not MANIFEST.is_file(),
    reason="T2.5 sources archive absent (Phase 0 manual download not done)",
)


def _entries() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_manifest_wellformed():
    for entry in _entries():
        assert entry.get("file"), "each entry needs a file name"
        assert entry.get("doc_role"), f"{entry.get('file')}: missing doc_role"
        assert entry.get("status") in {"pinned", "missing", "unobtainable"}, (
            f"{entry['file']}: unexpected status {entry.get('status')!r}"
        )


def test_pinned_sources_exist_and_match():
    for entry in _entries():
        if entry.get("status") != "pinned":
            continue
        path = SOURCES / entry["file"]
        assert path.is_file(), f"{entry['file']}: pinned but not on disk"
        assert path.stat().st_size == entry["bytes"], f"{entry['file']}: byte-count drift"
        assert _sha256(path) == entry["sha256"], (
            f"{entry['file']}: sha256 mismatch (provenance break)"
        )
