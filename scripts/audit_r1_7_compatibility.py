"""Audit archived signed dev requests without restoring an active failed trial."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.eval.collaboration_staging import (
    _resolve_cli_staging_base,
    load_staging_manifest,
)
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationSubagentRequest,
)

ARCHIVE = Path("data/eval/legacy/m4-config4/lineage-1-r1_2-failed/train-dev/adaptive_agent")
ORIGINAL = Path("data/eval/m4/lineage/train-dev/adaptive_agent")
ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_archive(root: Path, *, expected_count: int = 102) -> dict:
    root = root.resolve()
    base = root / ARCHIVE
    preparation_path = base / "request-preparation.json"
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    rows = preparation["request_order"]
    if preparation["task_count"] != expected_count or len(rows) != expected_count:
        raise ValueError("archived signed-request denominator differs")
    if len({row["run_key"] for row in rows}) != expected_count:
        raise ValueError("duplicate archived request run key")
    pins = []
    for ordinal, row in enumerate(rows, 1):
        key = row["run_key"]
        if row["ordinal"] != ordinal:
            raise ValueError("archived request order differs")
        if row["request_path"] != (ORIGINAL / "requests" / f"{key}.json").as_posix():
            raise ValueError("unexpected original signed request path")
        if row["staging_path"] != (ORIGINAL / "task-staging" / key).as_posix():
            raise ValueError("unexpected original staging path")
        request_path = base / "requests" / f"{key}.json"
        if _sha(request_path) != row["request_artifact_sha256"]:
            raise ValueError("archived request artifact checksum differs")
        request = CollaborationSubagentRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        if request.run_key != key or request.request_sha256 != row["request_sha256"]:
            raise ValueError("archived request model identity differs")
        manifest_path = base / "task-staging" / key / "staging-manifest.json"
        if _sha(manifest_path) != row["staging_manifest_sha256"]:
            raise ValueError("archived staging manifest checksum differs")
        load_staging_manifest(
            staging_base=base / "task-staging",
            run_key=key,
            expected_staging_sha256=row["staging_sha256"],
        )
        pins.append({
            "run_key": key,
            "request_artifact_sha256": row["request_artifact_sha256"],
            "request_sha256": request.request_sha256,
            "prompt_sha256": request.prompt_sha256,
            "staging_manifest_sha256": row["staging_manifest_sha256"],
            "staging_sha256": row["staging_sha256"],
        })
    archive_stage = base / "task-staging"
    if _resolve_cli_staging_base(archive_stage, root=root) != archive_stage.resolve():
        raise ValueError("archive path unexpectedly remapped")
    return {
        "schema_version": "r1.7-signed-dev-compatibility-v1",
        "status": "ARCHIVED_SIGNED_BYTES_AND_STAGING_VERIFIED",
        "request_count": expected_count,
        "request_preparation_path": (ARCHIVE / "request-preparation.json").as_posix(),
        "request_preparation_sha256": _sha(preparation_path),
        "exact_prompt_and_request_bytes_preserved": True,
        "archived_staging_file_checksums_verified": True,
        "original_canonical_trial_present": (root / ORIGINAL).exists(),
        "archive_is_active_cli_alias": False,
        "historical_trial_state": "TERMINAL_FAILED_TRIAL_ARCHIVED",
        "compatibility_limitation": (
            "The exact historical CLI mapping is unchanged, but its canonical failed "
            "trial directory is absent. Archived paths are not remapped to a live trial; "
            "this byte-integrity audit does not claim the archived prompts are executable "
            "through their original command paths."
        ),
        "provider_calls_performed": 0,
        "requests_or_runtime_modified": False,
        "requests": pins,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = audit_archive(ROOT)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Verified {receipt['request_count']} archived signed requests and staging trees")


if __name__ == "__main__":
    main()
