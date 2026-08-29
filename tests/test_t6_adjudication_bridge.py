from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.benchmark.t6_adjudication import (
    AIAdjudicationAuditManifest,
    AIAdjudicationItemAudit,
    AIAdjudicationResponseRecord,
)
from cobol_archaeologist.benchmark.t6_adjudication_bridge import (
    build_ai_adjudication_promotion_bridge,
    validate_ai_adjudication_promotion_bridge,
)
from cobol_archaeologist.benchmark.t6_review import (
    CollaborationSubagentAttemptAudit,
    ReviewArtifactMetadata,
    ReviewResponse,
    SequentialDeliveryAuditEntry,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    load_blinded_review_packet,
)

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "data/benchmark/t6-v2/review/packet.jsonl"
POLICY = ROOT / "data/benchmark/t6-v2/review/release-policy.json"
SCHEMA = ROOT / "data/benchmark/t6-v2/review/response.schema.json"


def _pin(path: Path) -> ArtifactPin:
    return ArtifactPin(
        path=path.resolve().relative_to(ROOT).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_ai_adjudication_bridge_projects_exact_promotion_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    item = load_blinded_review_packet(PACKET)[0]
    response = ReviewResponse(
        decision="include",
        drift_type="D7_conformant",
        line_level=[],
        rationale="The visible implementation conforms.",
        uncertainty_notes=None,
    )
    primary = {"decision": "include", "drift_type": "D7_conformant"}
    independent = {"decision": "include", "drift_type": "D1_stale_threshold"}
    dimensions = ["drift_type"]
    visible = {
        "review_item_id": item.review_item_id,
        "authority": item.authority.model_dump(mode="json"),
        "source_alias": item.source_alias,
        "source_text": item.source_text,
    }
    compact = lambda value: json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    visible_bytes = compact(visible)
    primary_bytes = compact(primary)
    independent_bytes = compact(independent)
    dimensions_bytes = compact(dimensions)
    prompt = b"\n".join(
        [
            b"Envelope: " + visible_bytes,
            b"Primary response: " + primary_bytes,
            b"Independent response: " + independent_bytes,
            b"Disagreement dimensions: " + dimensions_bytes,
        ]
    )
    final = response.model_dump_json().encode("utf-8")
    task = "/root/test/adjudicate-o01"
    source_responses = tmp_path / "responses.jsonl"
    source_responses.write_text(
        AIAdjudicationResponseRecord(
            schema_version="1",
            review_role="ai_adjudicator",
            release_ordinal=item.release_ordinal,
            review_item_id=item.review_item_id,
            task_identity=task,
            attempt=1,
            review_response=response,
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    attempt = CollaborationSubagentAttemptAudit(
        attempt=1,
        task_identity=task,
        fork_turns="none",
        model_id="gpt-5.6-luna",
        reasoning_effort="max",
        tools_authorized=0,
        prior_item_context_included=False,
        visible_review_items=1,
        staged_source_bundles=0,
        envelope_format="visible_canonical",
        envelope_separator="space",
        prompt_envelope_sha256=hashlib.sha256(visible_bytes).hexdigest(),
        prompt_utf8_base64=base64.b64encode(prompt).decode(),
        prompt_utf8_length=len(prompt),
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        final_message_utf8_base64=base64.b64encode(final).decode(),
        final_message_utf8_length=len(final),
        final_message_sha256=hashlib.sha256(final).hexdigest(),
        outcome="accepted",
    )
    input_bytes = b"\n".join(
        [visible_bytes, primary_bytes, independent_bytes, dimensions_bytes]
    )
    audit = AIAdjudicationAuditManifest(
        schema_version="1",
        audit_variant="ai_adjudicator_collaboration_subagent",
        finalized=True,
        review_role="ai_adjudicator",
        reviewer_pseudonym="luna-max-ai-adjudicator",
        comparison_report=_pin(PACKET),
        packet=_pin(PACKET),
        response_schema=_pin(SCHEMA),
        primary_responses=_pin(PACKET),
        independent_responses=_pin(PACKET),
        responses=_pin(source_responses),
        provider="chatgpt-codex-collaboration",
        model_id="gpt-5.6-luna",
        reasoning_effort="max",
        fork_turns_per_attempt="none",
        fresh_task_per_attempt=True,
        visible_review_items_per_call=1,
        staged_source_bundles_per_call=0,
        tools_authorized_per_call=0,
        prior_item_context_included=False,
        native_execution_bundle_claimed=False,
        item_count=1,
        accepted_count=1,
        schema_invalid_attempt_count=0,
        retry_count=0,
        release_ordinal_order=[item.release_ordinal],
        review_item_order=[item.review_item_id],
        items=[
            AIAdjudicationItemAudit(
                release_ordinal=item.release_ordinal,
                review_item_id=item.review_item_id,
                source_alias=item.source_alias,
                source_envelope_sha256=hashlib.sha256(visible_bytes).hexdigest(),
                primary_response_sha256=hashlib.sha256(primary_bytes).hexdigest(),
                independent_response_sha256=hashlib.sha256(
                    independent_bytes
                ).hexdigest(),
                disagreement_dimensions=dimensions,
                adjudication_input_sha256=hashlib.sha256(input_bytes).hexdigest(),
                attempts=[attempt],
            )
        ],
    )
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(audit.model_dump_json(indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "cobol_archaeologist.benchmark.t6_adjudication_bridge.validate_ai_adjudication_audit",
        lambda **_kwargs: audit,
    )

    bridge = build_ai_adjudication_promotion_bridge(
        root=ROOT,
        audit_manifest_path=audit_path,
        release_policy_path=POLICY,
        output_dir=tmp_path / "bridge",
    )
    validated = validate_ai_adjudication_promotion_bridge(
        root=ROOT,
        bridge_path=tmp_path / "bridge/promotion-bridge-manifest.json",
    )
    metadata = ReviewArtifactMetadata.model_validate_json(
        (ROOT / bridge.adjudication_metadata.path).read_text(encoding="utf-8")
    )
    delivery = SequentialDeliveryAuditEntry.model_validate_json(
        (ROOT / bridge.sequential_delivery_audit.path).read_text(encoding="utf-8")
    )

    assert validated == bridge
    assert metadata.reviewer_pseudonym == audit.reviewer_pseudonym
    assert metadata.expected_item_count == 1
    assert metadata.responses == bridge.adjudication_responses
    assert delivery.release_ordinal == item.release_ordinal
