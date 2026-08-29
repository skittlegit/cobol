"""Build and validate byte-exact collaboration evidence for T6 adjudication."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.benchmark.t6_adjudication import (
    AIAdjudicationAuditManifest,
    AIAdjudicationItemAudit,
    AIAdjudicationResponseRecord,
    validate_ai_adjudication_audit,
)
from cobol_archaeologist.benchmark.t6_review import (
    CollaborationSubagentAttemptAudit,
    ReviewResponse,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin, load_blinded_review_packet

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/benchmark/t6-v2/review"
COMPARISON = REVIEW / "evidence/comparison/primary-vs-luna.final.json"
PACKET = REVIEW / "packet.jsonl"
SCHEMA = REVIEW / "response.schema.json"
PRIMARY = REVIEW / "ai-primary-collaboration/responses.jsonl"
INDEPENDENT = (
    REVIEW
    / "evidence/luna-independent-collaboration-subagent/responses.jsonl"
)
OUTPUT = REVIEW / "evidence/ai-adjudicator-collaboration-subagent"
RESULTS = OUTPUT / "accepted-results.jsonl"


def _compact(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pin(path: Path) -> ArtifactPin:
    return ArtifactPin(
        path=path.relative_to(ROOT).as_posix(), sha256=_sha_bytes(path.read_bytes())
    )


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _inputs() -> list[dict[str, object]]:
    packet = {item.review_item_id: item for item in load_blinded_review_packet(PACKET)}
    primary = {row["review_item_id"]: row for row in _rows(PRIMARY)}
    independent = {row["review_item_id"]: row for row in _rows(INDEPENDENT)}
    comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
    result = []
    for dispute in comparison["items"]:
        if not dispute["requires_adjudication_review"]:
            continue
        item = packet[dispute["review_item_id"]]
        visible = {
            "review_item_id": item.review_item_id,
            "authority": item.authority.model_dump(mode="json"),
            "source_alias": item.source_alias,
            "source_text": item.source_text,
        }
        result.append(
            {
                "release_ordinal": dispute["release_ordinal"],
                "review_item_id": item.review_item_id,
                "source_alias": item.source_alias,
                "visible": visible,
                "primary": primary[item.review_item_id]["review_response"],
                "independent": independent[item.review_item_id]["review_response"],
                "dimensions": dispute["disagreement_dimensions"],
            }
        )
    return result


def _prompt(row: dict[str, object], *, attempt: int) -> bytes:
    visible = _compact(row["visible"])
    primary = _compact(row["primary"])
    independent = _compact(row["independent"])
    dimensions = _compact(row["dimensions"])
    return (
        "You are the non-human ai_adjudicator for exactly one blinded COBOL/authority "
        "dispute. Use only the single envelope and the two judgments below. You have "
        "no access to pair membership, proposals, canonical paths, other items, prior "
        "responses, or tools. Do not call tools. Resolve the listed disagreement "
        "dimensions from the visible authority and source; do not merely vote between "
        "the judgments. Return only one JSON object with exactly these keys: decision, "
        "drift_type, line_level, rationale, uncertainty_notes. decision must be include "
        "or exclude, never needs_adjudication. drift_type must be one of "
        "D1_stale_threshold|D2_missing_rule|D3_contradictory|D4_stale_reference_data|"
        "D5_boundary_error|D6_dead_code|D7_conformant or null. line_level must contain "
        "only objects with program, integer line >= 1, and the visible source_alias. "
        "Excluded items require null drift_type and no citations. Included items require "
        "a drift_type. D7 requires no citations; every non-D7 result requires at least "
        "one citation. Do not infer or discuss a temporal partner.\n"
        f"Fresh isolated attempt: {attempt}\n"
        "Envelope: "
    ).encode() + visible + b"\nPrimary response: " + primary + b"\nIndependent response: " + independent + b"\nDisagreement dimensions: " + dimensions


def emit_prompt(ordinal: int, attempt: int) -> None:
    row = next(row for row in _inputs() if row["release_ordinal"] == ordinal)
    print(_prompt(row, attempt=attempt).decode())


def seal() -> None:
    accepted = {row["release_ordinal"]: row for row in _rows(RESULTS)}
    inputs = _inputs()
    missing = [row["release_ordinal"] for row in inputs if row["release_ordinal"] not in accepted]
    if missing:
        raise SystemExit(f"missing adjudication results: {missing}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    response_records = []
    audits = []
    for row in inputs:
        ordinal = row["release_ordinal"]
        result = accepted[ordinal]
        attempt = int(result["attempt"])
        prompt = _prompt(row, attempt=attempt)
        final = result["final_json"].encode()
        parsed = ReviewResponse.model_validate_json(final)
        task = str(result["task_identity"])
        attempt_audit = CollaborationSubagentAttemptAudit(
            attempt=attempt,
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
            prompt_envelope_sha256=_sha_bytes(_compact(row["visible"])),
            prompt_utf8_base64=base64.b64encode(prompt).decode(),
            prompt_utf8_length=len(prompt),
            prompt_sha256=_sha_bytes(prompt),
            final_message_utf8_base64=base64.b64encode(final).decode(),
            final_message_utf8_length=len(final),
            final_message_sha256=_sha_bytes(final),
            outcome="accepted",
        )
        primary = _compact(row["primary"])
        independent = _compact(row["independent"])
        dimensions = _compact(row["dimensions"])
        input_bytes = b"\n".join([_compact(row["visible"]), primary, independent, dimensions])
        audits.append(
            AIAdjudicationItemAudit(
                release_ordinal=ordinal,
                review_item_id=row["review_item_id"],
                source_alias=row["source_alias"],
                source_envelope_sha256=_sha_bytes(_compact(row["visible"])),
                primary_response_sha256=_sha_bytes(primary),
                independent_response_sha256=_sha_bytes(independent),
                disagreement_dimensions=row["dimensions"],
                adjudication_input_sha256=_sha_bytes(input_bytes),
                attempts=[attempt_audit],
            )
        )
        response_records.append(
            AIAdjudicationResponseRecord(
                schema_version="1",
                review_role="ai_adjudicator",
                release_ordinal=ordinal,
                review_item_id=row["review_item_id"],
                task_identity=task,
                attempt=attempt,
                review_response=parsed,
            )
        )
    responses_path = OUTPUT / "responses.jsonl"
    responses_path.write_text(
        "".join(record.model_dump_json() + "\n" for record in response_records),
        encoding="utf-8",
        newline="\n",
    )
    manifest = AIAdjudicationAuditManifest(
        schema_version="1",
        audit_variant="ai_adjudicator_collaboration_subagent",
        finalized=True,
        review_role="ai_adjudicator",
        reviewer_pseudonym="luna-max-ai-adjudicator",
        comparison_report=_pin(COMPARISON),
        packet=_pin(PACKET),
        response_schema=_pin(SCHEMA),
        primary_responses=_pin(PRIMARY),
        independent_responses=_pin(INDEPENDENT),
        responses=_pin(responses_path),
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
        item_count=len(audits),
        accepted_count=len(audits),
        schema_invalid_attempt_count=0,
        retry_count=0,
        release_ordinal_order=[audit.release_ordinal for audit in audits],
        review_item_order=[audit.review_item_id for audit in audits],
        items=audits,
    )
    manifest_path = OUTPUT / "audit-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validate_ai_adjudication_audit(root=ROOT, manifest_path=manifest_path)
    print(manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-prompt", type=int)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    if args.emit_prompt is not None:
        emit_prompt(args.emit_prompt, args.attempt)
    elif args.seal:
        seal()
    else:
        parser.error("choose --emit-prompt or --seal")


if __name__ == "__main__":
    main()
