"""Seal the fresh 22-item Luna collaboration pass from its exact transcript."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_t6_collaboration_audit import build

TASK_IDENTITIES = [
    *[
        f"/root/luna_independent_review_coordinator/independent_review_{ordinal:02d}_attempt_1"
        for ordinal in range(1, 21)
    ],
    "/root/ai_primary_protocol/luna_t6_o21",
    "/root/ai_primary_protocol/luna_t6_o22",
]

FINAL_MESSAGES = [
    '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program identifies a beneficial owner when capital or profit entitlement is strictly greater than 15 percent, matching the authority threshold and comparator.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5D","line":12,"source_alias":"src-399485528ad0"}],"rationale":"The upload is triggered only by a received flag; the source contains no rule enforcing completion within 7 days of receiving updated customer information.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program uploads when updated information is received and imposes no time-bound deadline, matching the stated no_deadline rule.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The source applies a strictly-greater-than 15 percent threshold to either capital ownership or profit entitlement, matching the authority rule.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2P3A","line":17,"source_alias":"src-30e4dc6f71fe"},{"program":"T6V2P3A","line":22,"source_alias":"src-30e4dc6f71fe"}],"rationale":"The program calculates the due date by adding one calendar month rather than enforcing a maximum of 30 days; this yields 28, 29, 30, or 31 days depending on the complaint date.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2P4C","line":7,"source_alias":"src-1a17a05df960"},{"program":"T6V2P4C","line":17,"source_alias":"src-1a17a05df960"},{"program":"T6V2P4C","line":18,"source_alias":"src-1a17a05df960"}],"rationale":"The program defines and applies a 15 percent beneficial-owner threshold, while the authority requires strictly greater than 10 percent.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P3C","line":11,"source_alias":"src-f974d2ea86f7"},{"program":"T6V2CAL","line":30,"source_alias":"src-f974d2ea86f7"}],"rationale":"The visible implementation only computes and displays a next-month due date; it contains no rule for the unsatisfactory-response condition or the complainant\'s option to approach the concerned RBI Ombudsman.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2P4B","line":19,"source_alias":"src-040bc22d082a"},{"program":"T6V2P4B","line":23,"source_alias":"src-040bc22d082a"}],"rationale":"For partnership basis P, the program marks beneficial ownership only when WS-PROFIT-PCT > 15, while the authority requires strictly greater than 10 percent of capital or profits. The alternate capital path also uses the stale >15 threshold.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P3B","line":17,"source_alias":"src-e98bb3816dda"},{"program":"T6V2P3B","line":18,"source_alias":"src-e98bb3816dda"},{"program":"T6V2P3B","line":19,"source_alias":"src-e98bb3816dda"}],"rationale":"The program accepts a complaint date, calculates and displays a one-month due date, but contains no rule checking for an unsatisfactory issuer response and no implementation of the complainant\'s option to approach the RBI Ombudsman required by clause 26(c).","uncertainty_notes":"The calendar-month calculation itself matches the stated maximum period."}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5C","line":12,"source_alias":"src-e3ef336cfd4e"}],"rationale":"The program only performs a local audit routine and conditionally marks the status as submitted; it contains no seven-day deadline enforcement or Central KYC Records Registry update logic.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5A","line":14,"source_alias":"src-706c34d3f1ea"}],"rationale":"The program marks the registry update as uploaded when the received flag is Y, but contains no rule enforcing completion within 7 days of receiving updated information.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2CAL","line":30,"source_alias":"src-fd52bd92e519"}],"rationale":"T6V2CAL computes the due date by adding one calendar month at line 30, which can represent 28, 29, 30, or 31 days and does not implement the authority\'s maximum 30-day period.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program marks the beneficial owner when capital or profit entitlement is strictly greater than 15%, matching the authority threshold and comparator.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2P4A","line":19,"source_alias":"src-b861240e660d"},{"program":"T6V2P4A","line":23,"source_alias":"src-b861240e660d"}],"rationale":"Both capital and profit checks use a strictly-greater-than 15 percent threshold, while the authority requires strictly greater than 10 percent.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5B","line":18,"source_alias":"src-70bad6c473b1"}],"rationale":"The upload routine marks a record as uploaded but contains no receipt-time data or logic enforcing the required at-most-7-day KYC update deadline.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P3A","line":17,"source_alias":"src-838f86440cf8"},{"program":"T6V2P3A","line":18,"source_alias":"src-838f86440cf8"}],"rationale":"The program only computes and displays a date one calendar month after lodging. It contains no rule assessing whether the issuer provided a satisfactory response or enabling the complainant\'s option to approach the RBI Ombudsman after an unsatisfactory response within one month.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2BOSV","line":28,"source_alias":"src-b19527e0f99c"}],"rationale":"The beneficial-owner test uses a strictly greater-than 15 percent threshold for capital or profits, while the authority requires strictly greater than 10 percent.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program uploads the customer record when updated information is received and imposes no time-bound deadline, matching clause (h).","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P4B","line":18,"source_alias":"src-32ee576a480f"},{"program":"T6V2P4B","line":19,"source_alias":"src-32ee576a480f"},{"program":"T6V2P4B","line":23,"source_alias":"src-32ee576a480f"},{"program":"T6V2P4B","line":24,"source_alias":"src-32ee576a480f"}],"rationale":"For partnership firms, the authority requires beneficial-owner status when capital or profits exceed 15 percent. The source branches on WS-OWNERSHIP-BASIS and checks only one metric, so it omits the required capital-or-profits rule.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5C","line":16,"source_alias":"src-b51954cf8a21"}],"rationale":"Submission is gated only on WS-UPDATE-RECEIVED = \'Y\'; the visible program has no periodic-updation path required by clause (h), although it does not impose a time deadline.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2P3B","line":18,"source_alias":"src-4e650c566fad"},{"program":"T6V2P3B","line":23,"source_alias":"src-4e650c566fad"}],"rationale":"The program computes the deadline by adding one calendar month rather than enforcing a maximum of 30 days from complaint lodging. A calendar month can span 28, 29, 30, or 31 days, causing a boundary mismatch with the authority rule.","uncertainty_notes":null}',
    '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The source uploads customer records without imposing any update-deadline, consistent with the authority\'s stated absence of a time-bound deadline.","uncertainty_notes":null}',
]

FIRST_TEMPLATE = (
    "You are the independent_verifier reviewer for exactly one blinded COBOL/authority "
    "judgment. Use only the single envelope below. Do not use tools, files, web, other "
    "items, prior responses, pair membership, proposals, canonical paths, candidate "
    "specs, diagnostics, or tests. Localize any non-conformity directly in the visible "
    "source. Do not infer or discuss a temporal partner.\n\n"
    'Decision semantics: "include" means the item is valid and evaluable, whether it '
    'exhibits drift or is D7_conformant. "exclude" is only for unusable or ambiguous '
    'evidence, not for conformant code. Use "needs_adjudication" only when valid '
    "evidence leaves the label genuinely unresolved.\n\n"
    'Return only strict ReviewResponse JSON with exactly these fields: {"decision":'
    '"include|exclude|needs_adjudication","drift_type":"D1_stale_threshold|'
    'D2_missing_rule|D3_contradictory|D4_stale_reference_data|D5_boundary_error|'
    'D6_dead_code|D7_conformant|null","line_level":[{"program":"nonempty","line":1,'
    '"source_alias":"src-12hex"}],"rationale":"nonempty","uncertainty_notes":'
    '"string or null"}. No markdown or extra text. Excluded items require null '
    "drift_type and empty line_level. Included items require non-null drift_type. D7 "
    "requires empty line_level. Every non-D7 label requires at least one citation "
    "using exact visible program, 1-based line number, and source_alias.\n\n"
    "Fresh isolated attempt: 1\nEnvelope: "
)

FINAL_TEMPLATE = (
    "You are the independent_verifier reviewer for exactly one blinded COBOL/authority "
    "judgment. Use only the single envelope below. You have no access to pair membership, "
    "proposals, canonical paths, other items, prior responses, or tools. Do not call any "
    "tool or inspect any file. Localize any non-conformity directly in the visible source. "
    "Return only one JSON object with exactly these keys and constraints: decision is "
    "include|exclude|needs_adjudication; drift_type is one of D1_stale_threshold|"
    "D2_missing_rule|D3_contradictory|D4_stale_reference_data|D5_boundary_error|"
    "D6_dead_code|D7_conformant or null; line_level is an array of objects each with "
    "exactly program (nonempty string), line (integer >=1), source_alias matching "
    "^src-[0-9a-f]{12}$; rationale is a nonempty string; uncertainty_notes is string or "
    "null. Excluded items must have null drift_type and no citations. Included items "
    "require drift_type. D7 requires no line citations; every non-D7 label requires at "
    "least one citation. Do not infer or discuss a temporal partner.\n"
    "Fresh isolated attempt: 1\nEnvelope: "
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = root / "data/benchmark/t6-v2/review/packet.jsonl"
    rows = [
        json.loads(raw)
        for raw in packet_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    transcripts = []
    for ordinal, (row, task_identity, final_message) in enumerate(
        zip(rows, TASK_IDENTITIES, FINAL_MESSAGES, strict=True), start=1
    ):
        visible = {
            key: row[key]
            for key in ("review_item_id", "authority", "source_alias", "source_text")
        }
        envelope = json.dumps(
            visible, ensure_ascii=False, separators=(",", ":")
        )
        template = FIRST_TEMPLATE if ordinal <= 20 else FINAL_TEMPLATE
        transcripts.append(
            {
                "release_ordinal": ordinal,
                "review_item_id": row["review_item_id"],
                "attempts": [
                    {
                        "attempt": 1,
                        "task_identity": task_identity,
                        "prompt": template + envelope,
                        "final_message": final_message,
                        "outcome": "accepted",
                        "envelope_format": "visible_canonical",
                        "envelope_separator": "space",
                    }
                ],
            }
        )
    prompt_21 = transcripts[20]["attempts"][0]["prompt"].encode("utf-8")
    prompt_22 = transcripts[21]["attempts"][0]["prompt"].encode("utf-8")
    import hashlib

    expected = (
        (3143, "bedc851dde4ed8cf8ed8da65897c6fc35be8ca64fbed2698fb133d8c0cd41e4b"),
        (2476, "793e3b5a4d24fd00c03e5d90b5f5e70138aa9518cebee51c0d4e3923ad8e84fb"),
    )
    for raw, (length, digest) in zip((prompt_21, prompt_22), expected, strict=True):
        if len(raw) != length or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("protocol-agent prompt bytes do not match their frozen pin")
    transcript_path = output_dir / "transcript.jsonl"
    transcript_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in transcripts
        ),
        encoding="utf-8",
    )
    build(
        argparse.Namespace(
            root=root,
            packet=packet_path,
            release_policy=root / "data/benchmark/t6-v2/review/release-policy.json",
            response_schema=root / "data/benchmark/t6-v2/review/response.schema.json",
            transcript=transcript_path,
            output_dir=output_dir,
            review_role="independent_verifier",
            reviewer_pseudonym=(
                "model_independent_verifier;model=gpt-5.6-luna;reasoning=max;"
                "fresh-pass=collaboration-subagent-v1"
            ),
        )
    )


if __name__ == "__main__":
    main()
