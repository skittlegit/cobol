#!/usr/bin/env python3
"""T2.5 Phase 1 - pin the archived RBI regulation PDFs by sha256.

Walks ``data/regulations/sources/*.pdf`` and writes ``sources/MANIFEST.json``
with one record per source: ``{file, doc_role, status, sha256, bytes, added}``.

Idempotent by design:
  * a file already pinned keeps its original ``added`` date;
  * re-pinning a file whose bytes changed is a PROVENANCE BREAK -> hard error
    (the archive must never silently swap a hash), not a quiet update.

Expected-but-absent sources are recorded with ``status: "missing"`` so a
downstream step can mark the affected T6 pair *degraded* rather than substitute
a secondary source. A source the user has confirmed cannot be located should be
hand-edited to ``status: "unobtainable"`` in MANIFEST.json; this script
preserves that.

Phase 0 (obtaining the PDFs) is a manual [USER] step; drop the seven files named
in the roster below into ``data/regulations/sources/`` and run this script.

Usage:
    python scripts/pin_regulations.py          # (re)write MANIFEST.json
    python scripts/pin_regulations.py --check   # verify hashes, no write (exit 1 on drift)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = REPO_ROOT / "data" / "regulations" / "sources"
MANIFEST = SOURCES_DIR / "MANIFEST.json"

# Expected archive roster (T2.5 work order, Phase 0 table): filename -> doc_role.
EXPECTED: dict[str, str] = {
    "cc-dc-directions-2025.pdf": "cc_2025_current_anchor",
    "cc-md-2022-as-issued.pdf": "cc_2022_as_issued",
    "cc-md-2022-consol-2024.pdf": "cc_2022_consolidated_2024",
    "kyc-directions-2025.pdf": "kyc_2025",
    "kyc-md-2016-final-consol.pdf": "kyc_2016_final_consolidation",
    "kyc-md-2016-consol-pre-2023-10.pdf": "kyc_2016_pre_2023_10_consolidation",
    "kyc-amend-2023-10-17.pdf": "kyc_amendment_2023_10_17",
    "kyc-amend-2024-11-06.pdf": "kyc_amendment_2024_11_06",
}


def sha256_of(path: Path) -> tuple[str, int]:
    """Return (hex digest, byte count) streamed in 1 MiB chunks."""
    h = hashlib.sha256()
    nbytes = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            nbytes += len(chunk)
    return h.hexdigest(), nbytes


def load_prior() -> dict[str, dict]:
    if not MANIFEST.is_file():
        return {}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {entry["file"]: entry for entry in data.get("entries", [])}


def build_entries(prior: dict[str, dict]) -> list[dict]:
    today = datetime.date.today().isoformat()
    present = (
        {p.name for p in SOURCES_DIR.glob("*.pdf")} if SOURCES_DIR.is_dir() else set()
    )
    # Roster = expected files plus any extra PDFs actually dropped in.
    names = sorted(set(EXPECTED) | present)
    entries: list[dict] = []
    for name in names:
        role = EXPECTED.get(name, "unlisted")
        path = SOURCES_DIR / name
        old = prior.get(name, {})
        if path.is_file():
            digest, nbytes = sha256_of(path)
            if old.get("sha256") and old["sha256"] != digest:
                raise SystemExit(
                    f"PROVENANCE BREAK: {name} hash changed\n"
                    f"  was {old['sha256']}\n"
                    f"  now {digest}\n"
                    "Refusing to overwrite. If this re-archive is intentional, "
                    "delete the stale entry from MANIFEST.json by hand first."
                )
            entry = {
                "file": name,
                **{
                    key: old[key]
                    for key in ("doc", "version", "effective_date")
                    if key in old
                },
                "doc_role": role,
                "status": "pinned",
                "sha256": digest,
                "bytes": nbytes,
                "added": old.get("added", today),
            }
            # A hand-written provenance caveat (e.g. "this source documents the
            # amendment event but does not quote the numeric threshold") survives
            # re-runs on pinned entries too.
            if old.get("note"):
                entry["note"] = old["note"]
            entries.append(entry)
        else:
            # Preserve a user-confirmed 'unobtainable'; otherwise not-yet-downloaded.
            status = "unobtainable" if old.get("status") == "unobtainable" else "missing"
            entry = {"file": name, "doc_role": role, "status": status}
            # Preserve a hand-written provenance note across re-runs (e.g. "which
            # specific PDF to fetch and why the previous download was incomplete").
            if old.get("note"):
                entry["note"] = old["note"]
            entries.append(entry)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify pinned hashes without rewriting MANIFEST.json (exit 1 on drift)",
    )
    args = parser.parse_args()

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    prior = load_prior()

    if args.check:
        ok = True
        for name, entry in prior.items():
            if entry.get("status") != "pinned":
                continue
            path = SOURCES_DIR / name
            if not path.is_file():
                print(f"MISSING  {name}: pinned in MANIFEST but not on disk")
                ok = False
                continue
            digest, _ = sha256_of(path)
            if digest != entry.get("sha256"):
                print(f"MISMATCH {name}: {digest} != {entry.get('sha256')}")
                ok = False
        print("check: OK" if ok else "check: FAILED")
        return 0 if ok else 1

    entries = build_entries(prior)
    pinned = [e for e in entries if e["status"] == "pinned"]
    absent = [e for e in entries if e["status"] != "pinned"]

    manifest = {
        "note": (
            "T2.5 archive pins (sha256) of the primary RBI regulation PDFs. "
            "Generated by scripts/pin_regulations.py."
        ),
        "generated": datetime.date.today().isoformat(),
        "entries": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {MANIFEST.relative_to(REPO_ROOT)}: {len(pinned)} pinned, {len(absent)} absent")
    for e in absent:
        print(f"  [{e['status']:>12}] {e['file']}  ({e['doc_role']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
