from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin
from scripts.t6_review_coordinator import (
    CURRENT_NAME,
    DELIVERY_AUDIT_NAME,
    RESPONSES_NAME,
    STATE_NAME,
    finalize,
    initialize,
    record_response,
    release_next,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/benchmark/t6-v2/manifest.json"


def _response(item_id: str, reviewer: str) -> dict[str, object]:
    return {
        "review_item_id": item_id,
        "reviewer_pseudonym": reviewer,
        "completed_at": "2026-08-24T12:00:00Z",
        "review_response": {
            "decision": "exclude",
            "drift_type": None,
            "line_level": [],
            "rationale": "The reviewer excluded this synthetic workflow test item.",
            "uncertainty_notes": None,
        },
    }


def test_coordinator_exposes_at_most_one_item_and_never_retains_source_history(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ai-primary-workspace"
    reviewer = "model_ai_primary-a"
    initialize(
        root=ROOT,
        manifest_path=MANIFEST,
        workspace=workspace,
        reviewer_pseudonym=reviewer,
        review_role="ai_primary",
    )
    assert {path.name for path in workspace.iterdir()} == {STATE_NAME}

    first = release_next(root=ROOT, workspace=workspace)
    with pytest.raises(ValueError, match="already active"):
        release_next(root=ROOT, workspace=workspace)
    current = json.loads((workspace / CURRENT_NAME).read_text(encoding="utf-8"))
    assert current["review_item_id"] == first.review_item_id
    assert "source_text" in current
    assert "code_input_path" not in current
    assert "code_locus" not in current

    response_path = tmp_path / "response.json"
    response_path.write_text(
        json.dumps(_response(first.review_item_id, reviewer)), encoding="utf-8"
    )
    record_response(root=ROOT, workspace=workspace, response_path=response_path)
    assert not (workspace / CURRENT_NAME).exists()
    responses = (workspace / RESPONSES_NAME).read_text(encoding="utf-8")
    assert "source_text" not in responses
    assert first.source_alias not in responses

    second = release_next(root=ROOT, workspace=workspace)
    assert second.review_item_id != first.review_item_id
    active_text = (workspace / CURRENT_NAME).read_text(encoding="utf-8")
    assert first.source_alias not in active_text


def test_coordinator_completes_22_sequential_responses_and_freezes_metadata(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "complete-workspace"
    reviewer = "model_ai_primary-a"
    initialize(
        root=ROOT,
        manifest_path=MANIFEST,
        workspace=workspace,
        reviewer_pseudonym=reviewer,
        review_role="ai_primary",
    )
    response_path = tmp_path / "response.json"
    for _ in range(22):
        item = release_next(root=ROOT, workspace=workspace)
        response_path.write_text(
            json.dumps(_response(item.review_item_id, reviewer)), encoding="utf-8"
        )
        record_response(root=ROOT, workspace=workspace, response_path=response_path)

    with pytest.raises(ValueError, match="all 22"):
        release_next(root=ROOT, workspace=workspace)
    audit_path = tmp_path / "ai-primary-audit.json"
    audit_path.write_text("{}", encoding="utf-8")
    metadata_path = tmp_path / "ai-primary-metadata.json"
    metadata_pin = finalize(
        root=ROOT,
        workspace=workspace,
        metadata_path=metadata_path,
        controlled_model_audit_manifest=ArtifactPin(
            path=audit_path.relative_to(ROOT).as_posix(),
            sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        ),
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["expected_item_count"] == 22
    assert metadata["delivery_mode"] == "sequential_one_item"
    assert metadata["full_packet_distributed"] is False
    assert metadata["canonical_source_map_distributed"] is False
    assert metadata["sequential_delivery_audit"]["path"].endswith(DELIVERY_AUDIT_NAME)
    assert metadata_pin.sha256


def test_coordinator_rejects_response_for_nonactive_item(tmp_path: Path) -> None:
    workspace = tmp_path / "wrong-response-workspace"
    initialize(
        root=ROOT,
        manifest_path=MANIFEST,
        workspace=workspace,
        reviewer_pseudonym="model_ai_primary-a",
        review_role="ai_primary",
    )
    release_next(root=ROOT, workspace=workspace)
    response_path = tmp_path / "wrong-response.json"
    response_path.write_text(
        json.dumps(_response("rvw-00000000", "model_ai_primary-a")), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="differs from active"):
        record_response(root=ROOT, workspace=workspace, response_path=response_path)
    assert (workspace / CURRENT_NAME).exists()


def test_legacy_human_primary_role_is_rejected_instead_of_mislabeling_ai(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="ai_primary"):
        initialize(
            root=ROOT,
            manifest_path=MANIFEST,
            workspace=tmp_path / "blocked-human-workspace",
            reviewer_pseudonym="model_ai_primary-a",
            review_role="human_primary",
        )
