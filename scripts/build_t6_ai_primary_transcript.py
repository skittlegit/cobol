"""Materialize the byte-exact, non-human Sol/max T6 primary transcript."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT_TEMPLATE = """You are the {role} reviewer for exactly one blinded COBOL/authority judgment. Use only the single envelope below. You have no access to pair membership, proposals, canonical paths, other items, prior responses, or tools. Do not call any tool or inspect any file. Localize any non-conformity directly in the visible source. Return only one JSON object with exactly these keys and constraints: decision is include|exclude|needs_adjudication; drift_type is one of D1_stale_threshold|D2_missing_rule|D3_contradictory|D4_stale_reference_data|D5_boundary_error|D6_dead_code|D7_conformant or null; line_level is an array of objects each with exactly program (nonempty string), line (integer >=1), source_alias matching ^src-[0-9a-f]{12}$; rationale is a nonempty string; uncertainty_notes is string or null. Excluded items must have null drift_type and no citations. Included items require drift_type. D7 requires no line citations; every non-D7 label requires at least one citation. Do not infer or discuss a temporal partner.
Fresh isolated attempt: {attempt}
Envelope: {envelope}"""

STANDARD_TEMPLATE = """You are the isolated primary reviewer for exactly one blinded COBOL/authority item. You have no prior items or responses. Do not use tools, files, web, hidden context, or seek any other item. Judge only the single JSON envelope below. IMPORTANT decision semantics: decision=\"include\" means the item is valid and evaluable, whether it is drift or D7_conformant. Use decision=\"exclude\" only when the provided evidence is unusable or genuinely ambiguous for evaluation. Return ONLY strict ReviewResponse JSON with exactly: decision (include|exclude), drift_type (D1_stale_threshold|D2_missing_rule|D3_contradictory|D4_scope_mismatch|D5_temporal_semantics|D6_cross_module_inconsistency|D7_conformant|null), line_level (array of {program,line,source_alias}), rationale (nonempty string), uncertainty_notes (string|null). Excluded items require drift_type null and line_level []; D7 requires line_level []; every other included drift type requires at least one citation. Citations may reference only lines in source_text and must use the envelope source_alias. Envelope:
{envelope}"""

ORDINAL_THREE_TEMPLATE = """You are the isolated primary reviewer for exactly one blinded COBOL/authority item. You have no prior items or responses. Do not use tools, files, web, hidden context, or seek any other item. Judge only the single JSON envelope below. IMPORTANT decision semantics: decision=\"include\" means the item is valid and evaluable, whether it is drift or D7_conformant. Use decision=\"exclude\" only when the provided evidence is unusable or genuinely ambiguous for evaluation. Return ONLY strict ReviewResponse JSON with exactly: decision (include|exclude), drift_type (D1_stale_threshold|D2_missing_rule|D3_contradictory|D4_scope_mismatch|D5_temporal_semantics|D6_cross_module_inconsistency|D7_conformant|null), line_level (array of {program,line,source_alias} or null), rationale (nonempty string), uncertainty_notes (string|null). Citations may reference only lines in source_text and must use the envelope source_alias. For conformant, line_level should be empty. Envelope:
{envelope}"""

TASKS = {
    1: "/root/ai_primary_protocol/sol_t6_o01_rerun",
    2: "/root/ai_primary_protocol/sol_t6_o02_rerun",
    3: "/root/ai_primary_review_coordinator/primary_review_03_retry",
    4: "/root/ai_primary_protocol/sol_t6_o04_rerun",
    **{
        ordinal: f"/root/ai_primary_review_coordinator/primary_review_{ordinal:02d}"
        for ordinal in range(5, 23)
    },
}
TASKS[12] = "/root/ai_primary_review_coordinator/primary_review_12_exact"

FINAL_MESSAGES = {
    1: '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program applies a strictly greater-than 15 percent threshold to either capital or profits, matching the authority clause.","uncertainty_notes":null}',
    2: '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5D","line":12,"source_alias":"src-399485528ad0"},{"program":"T6V2UPLD","line":28,"source_alias":"src-399485528ad0"}],"rationale":"The update path invokes the upload solely when updated information is received, and the upload routine checks only for a nonblank customer ID. No receipt date, elapsed-time calculation, or control enforces completion within the required 7-day period.","uncertainty_notes":null}',
    3: '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program uploads the update when updated information is received (src-28f6e6298912, lines 14-15) and imposes no time-bound deadline, matching the authority version\'s no-deadline requirement.","uncertainty_notes":null}',
    4: '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P4A","line":18,"source_alias":"src-00dba01bdee6"},{"program":"T6V2P4A","line":22,"source_alias":"src-00dba01bdee6"}],"rationale":"The authority requires beneficial-owner identification when either capital entitlement or profit entitlement is strictly greater than 15%. The ownership-basis branch evaluates only one measure, so a customer exceeding the threshold on the unselected measure can be incorrectly classified as not a beneficial owner.","uncertainty_notes":null}',
    5: '{"decision":"include","drift_type":"D5_temporal_semantics","line_level":[{"program":"T6V2P3A","line":17,"source_alias":"src-30e4dc6f71fe"},{"program":"T6V2P3A","line":22,"source_alias":"src-30e4dc6f71fe"},{"program":"T6V2P3A","line":34,"source_alias":"src-30e4dc6f71fe"},{"program":"T6V2P3A","line":36,"source_alias":"src-30e4dc6f71fe"}],"rationale":"The authority specifies a fixed maximum period of 30 days from complaint lodging, but the program computes the due date by adding one calendar month and clamping the day to the destination month\'s length. A calendar month can represent 28, 29, 30, or 31 elapsed days, so this does not consistently enforce the required 30-day duration.","uncertainty_notes":null}',
    6: '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2P4C","line":7,"source_alias":"src-1a17a05df960"},{"program":"T6V2P4C","line":17,"source_alias":"src-1a17a05df960"},{"program":"T6V2P4C","line":18,"source_alias":"src-1a17a05df960"}],"rationale":"The program retains a 15 percent legacy threshold and applies a strictly-greater comparison to both capital and profit percentages. The current authority requires beneficial-owner identification when either percentage is strictly greater than 10 percent, so interests above 10 percent through 15 percent are incorrectly excluded.","uncertainty_notes":null}',
    7: '''{"decision":"include","drift_type":"D5_temporal_semantics","line_level":[{"program":"T6V2CAL","line":30,"source_alias":"src-f974d2ea86f7"},{"program":"T6V2CAL","line":35,"source_alias":"src-f974d2ea86f7"}],"rationale":"The routine increments the numeric month and copies the original day unchanged, so complaints lodged near a month end can produce nonexistent due dates such as 20230231. It therefore does not reliably implement a maximum period of one calendar month.","uncertainty_notes":"The authority does not specify whether 'one month' means a calendar month or a fixed number of days, but the generated invalid dates are defective under either reasonable interpretation."}''',
    8: '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2P4B","line":19,"source_alias":"src-040bc22d082a"},{"program":"T6V2P4B","line":23,"source_alias":"src-040bc22d082a"}],"rationale":"The program applies a strictly-greater-than 15 percent threshold to both profit entitlement and capital ownership, while the current authority requires a strictly-greater-than 10 percent threshold. This is a stale implementation of the pre-amendment threshold.","uncertainty_notes":null}',
    9: '{"decision":"include","drift_type":"D5_temporal_semantics","line_level":[{"program":"T6V2P3B","line":32,"source_alias":"src-e98bb3816dda"},{"program":"T6V2P3B","line":34,"source_alias":"src-e98bb3816dda"},{"program":"T6V2P3B","line":35,"source_alias":"src-e98bb3816dda"}],"rationale":"The program models the one-month period as a calendar-month increment, but its leap-year calculation checks only divisibility by 4. It therefore treats non-400-divisible century years such as 2100 as leap years and can produce February 29 as the due date, making the one-month deadline calculation temporally incorrect for those dates.","uncertainty_notes":null}',
    10: '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5C","line":16,"source_alias":"src-e3ef336cfd4e"},{"program":"T6V2P5C","line":17,"source_alias":"src-e3ef336cfd4e"},{"program":"T6V2P5C","line":18,"source_alias":"src-e3ef336cfd4e"}],"rationale":"The submission logic marks an update as submitted when an update was received and a submission ID exists, but it contains no rule or date calculation enforcing submission to the registry within 7 days of receipt.","uncertainty_notes":null}',
    11: '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5A","line":14,"source_alias":"src-706c34d3f1ea"},{"program":"T6V2P5A","line":15,"source_alias":"src-706c34d3f1ea"}],"rationale":"The upload logic reacts to a received-update flag and marks the record uploaded, but it contains no date capture, elapsed-time calculation, or enforcement of the required maximum seven-day update window.","uncertainty_notes":null}',
    12: '{"decision":"include","drift_type":"D5_temporal_semantics","line_level":[{"program":"T6V2CAL","line":30,"source_alias":"src-fd52bd92e519"},{"program":"T6V2CAL","line":35,"source_alias":"src-fd52bd92e519"}],"rationale":"The authority specifies a maximum elapsed period of 30 days, but T6V2CAL advances the month by one and preserves the day-of-month, implementing a calendar-month interval rather than 30 days. This can yield intervals of 28, 29, or 31 days and therefore can exceed the permitted maximum.","uncertainty_notes":null}',
    13: '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"T6V2BOSV identifies a beneficial owner when either capital ownership or profit entitlement is strictly greater than 15 percent, matching the authority\'s threshold and comparator.","uncertainty_notes":null}',
    14: '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2P4A","line":19,"source_alias":"src-b861240e660d"},{"program":"T6V2P4A","line":23,"source_alias":"src-b861240e660d"}],"rationale":"The program applies a strictly-greater-than 15 percent threshold to both capital ownership and profit entitlement, while the cited authority requires a strictly-greater-than 10 percent threshold. The implemented comparator is correct, but the threshold is stale.","uncertainty_notes":null}',
    15: '{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P5B","line":14,"source_alias":"src-70bad6c473b1"},{"program":"T6V2P5B","line":15,"source_alias":"src-70bad6c473b1"}],"rationale":"The queue-processing flow accepts a customer identifier and uploads the record without capturing when updated information was received or enforcing the required maximum seven-day update period. The mandated temporal rule is therefore missing.","uncertainty_notes":null}',
    16: '{"decision":"include","drift_type":"D5_temporal_semantics","line_level":[{"program":"T6V2P3A","line":31,"source_alias":"src-838f86440cf8"},{"program":"T6V2P3A","line":32,"source_alias":"src-838f86440cf8"}],"rationale":"The program implements one month as a calendar-month increment but always limits February to 28 days. It therefore mishandles leap years—for example, a complaint lodged on January 29 in a leap year produces February 28 rather than February 29—altering the maximum one-month waiting period.","uncertainty_notes":null}',
    17: '{"decision":"include","drift_type":"D1_stale_threshold","line_level":[{"program":"T6V2BOSV","line":28,"source_alias":"src-b19527e0f99c"}],"rationale":"The beneficial-owner test uses a strictly-greater-than 15 percent threshold for both capital and profits, while the current authority requires a strictly-greater-than 10 percent threshold. This is a stale pre-amendment threshold.","uncertainty_notes":null}',
    18: '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The source implements an event-triggered upload when updated customer information is received and encodes no time-bound deadline, consistent with the cited 2018 authority state in which clause (h) required updating upon receipt or periodic updation but prescribed no fixed completion interval.","uncertainty_notes":null}',
    19: '''{"decision":"include","drift_type":"D2_missing_rule","line_level":[{"program":"T6V2P4B","line":18,"source_alias":"src-32ee576a480f"},{"program":"T6V2P4B","line":19,"source_alias":"src-32ee576a480f"},{"program":"T6V2P4B","line":23,"source_alias":"src-32ee576a480f"}],"rationale":"The authority requires beneficial-owner identification when either capital entitlement or profit entitlement is strictly greater than 15 percent. The program makes the two tests mutually exclusive based on WS-OWNERSHIP-BASIS, so it can omit a qualifying capital interest when the basis is 'P' or a qualifying profit interest otherwise. The missing rule is a combined capital-or-profits evaluation.","uncertainty_notes":null}''',
    20: '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program records a submitted audit status when updated information is received and a submission identifier exists, without imposing any time-bound deadline. This is consistent with the authority\'s no-deadline requirement.","uncertainty_notes":null}',
    21: '{"decision":"include","drift_type":"D5_temporal_semantics","line_level":[{"program":"T6V2P3B","line":18,"source_alias":"src-4e650c566fad"},{"program":"T6V2P3B","line":23,"source_alias":"src-4e650c566fad"},{"program":"T6V2P3B","line":41,"source_alias":"src-4e650c566fad"},{"program":"T6V2P3B","line":42,"source_alias":"src-4e650c566fad"},{"program":"T6V2P3B","line":43,"source_alias":"src-4e650c566fad"}],"rationale":"The authority specifies a maximum elapsed period of 30 days, but the program derives the due date by adding one calendar month and clamping the day to the destination month\'s length. A calendar month is not equivalent to 30 days and can produce deadlines both earlier and later than the required 30-day limit.","uncertainty_notes":null}',
    22: '{"decision":"include","drift_type":"D7_conformant","line_level":[],"rationale":"The program uploads each queued customer record without encoding or enforcing any time-bound update deadline, which is consistent with the cited authority\'s no-deadline requirement.","uncertainty_notes":null}',
}

ROOT_PROMPT_HASHES = {
    1: "6162fd3e0de86e061ebfdb768a66fb56194dd42bfd935f8fac8f41bb97edf3e7",
    2: "e6c527e9d1c7e6d681461933f64cfde85499db7429fd17a7a5f510667acf7f1e",
    4: "bdd7f2e9200894e6919dafe1ec53e891df2bc76c7211c2e8c9d661ef85d575e5",
}
SCHEMA_INVALID_RETRY_ORDINALS = {5, 7, 9, 12, 16, 21}
RETRY_TASKS = {
    5: "/root/ai_primary_protocol/sol_t6_o05_attempt2",
    7: "/root/ai_primary_protocol/sol_t6_o07_attempt2",
    9: "/root/ai_primary_protocol/sol_t6_o09_attempt2",
    12: "/root/ai_primary_protocol/sol_t6_o12_attempt2",
    16: "/root/ai_primary_protocol/sol_t6_o16_attempt2",
    21: "/root/ai_primary_protocol/sol_t6_o21_attempt2",
}
RETRY_PROMPT_PINS = {
    5: (2862, "75fd8b90fb3e19711fb855e5547dcdb05672bb990f59282787a4a80a5d1dec64"),
    7: (2824, "597d9959e191ab66722e0fd9083645b4fb255fbb174bf414060345e0b67f40c1"),
    9: (3140, "833a978206d2f54bc0e3aba218fb38ef8df26297a058de64e4343e2419735a67"),
    12: (2817, "60a3f644ee32728a834727685f817a9e7b17f76664273f0be05361caf8259344"),
    16: (2869, "36f4b306706252af4214d9e841d98d41d8b7384685083fff51a6177f71ecd6d9"),
    21: (3133, "da44655acc5b18316884fc6cd595108e1133182ba3bbc0e3ddb258f0c8f223b4"),
}
RETRY_FINAL_MESSAGES = {
    5: '{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2P3A","line":17,"source_alias":"src-30e4dc6f71fe"},{"program":"T6V2P3A","line":22,"source_alias":"src-30e4dc6f71fe"}],"rationale":"The program calculates the deadline by adding one calendar month rather than 30 elapsed days. Because calendar months vary in length, this can produce a deadline more than 30 days after complaint lodging, contrary to the maximum permitted period.","uncertainty_notes":null}',
    7: '''{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2CAL","line":30,"source_alias":"src-f974d2ea86f7"},{"program":"T6V2CAL","line":35,"source_alias":"src-f974d2ea86f7"}],"rationale":"The routine adds one to the month and preserves the original day without normalizing for the destination month's length. Complaints lodged near month-end can therefore produce impossible due dates such as 20230231, so the one-calendar-month boundary is implemented incorrectly.","uncertainty_notes":null}''',
    9: '{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2P3B","line":34,"source_alias":"src-e98bb3816dda"}],"rationale":"The calendar-month deadline calculation treats every year divisible by four as a leap year. It omits the Gregorian century exception, so dates rolling into February 2100, 2200, or 2300 can produce February 29 and exceed the correct one-month boundary by a day.","uncertainty_notes":null}',
    12: '''{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2CAL","line":30,"source_alias":"src-fd52bd92e519"},{"program":"T6V2CAL","line":35,"source_alias":"src-fd52bd92e519"}],"rationale":"The calculation advances the complaint date by one calendar month while retaining the day of month, rather than adding at most 30 days. This can produce a 31-day interval and can also create invalid dates, so it does not reliably enforce the authority's maximum 30-day boundary.","uncertainty_notes":null}''',
    16: '{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2P3A","line":32,"source_alias":"src-838f86440cf8"}],"rationale":"February is always capped at 28 days, so complaints lodged on January 29 in a leap year receive a February 28 due date instead of February 29. This miscomputes the one-calendar-month boundary for leap years.","uncertainty_notes":null}',
    21: '''{"decision":"include","drift_type":"D5_boundary_error","line_level":[{"program":"T6V2P3B","line":23,"source_alias":"src-4e650c566fad"}],"rationale":"The program computes the deadline by adding one calendar month rather than exactly 30 days, producing intervals of 28, 29, 30, or 31 days and therefore violating the authority's maximum 30-day period.","uncertainty_notes":null}''',
}


def build(packet_path: Path, output_path: Path) -> None:
    packet_lines = [line for line in packet_path.read_text(encoding="utf-8").splitlines() if line]
    if len(packet_lines) != 22:
        raise ValueError("expected 22 packet rows")
    rows: list[dict[str, object]] = []
    for ordinal, packet_line in enumerate(packet_lines, start=1):
        packet = json.loads(packet_line)
        if ordinal in ROOT_PROMPT_HASHES:
            visible = {
                key: packet[key]
                for key in ("review_item_id", "authority", "source_alias", "source_text")
            }
            envelope = json.dumps(visible, ensure_ascii=False, separators=(",", ":"))
            prompt = (
                ROOT_TEMPLATE.replace("{role}", "ai_primary")
                .replace("{attempt}", "1")
                .replace("{envelope}", envelope)
            )
            actual_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            if actual_hash != ROOT_PROMPT_HASHES[ordinal]:
                raise ValueError(f"ordinal {ordinal} root prompt bytes differ: {actual_hash}")
            envelope_format = "visible_canonical"
            envelope_separator = "space"
        else:
            template = ORDINAL_THREE_TEMPLATE if ordinal == 3 else STANDARD_TEMPLATE
            prompt = template.replace("{envelope}", packet_line)
            envelope_format = "full_blind_packet_row"
            envelope_separator = "lf"
        attempts = [
            {
                "attempt": 1,
                "task_identity": TASKS[ordinal],
                "prompt": prompt,
                "final_message": FINAL_MESSAGES[ordinal],
                "outcome": (
                    "schema_invalid"
                    if ordinal in SCHEMA_INVALID_RETRY_ORDINALS
                    else "accepted"
                ),
                "envelope_format": envelope_format,
                "envelope_separator": envelope_separator,
            }
        ]
        if ordinal in SCHEMA_INVALID_RETRY_ORDINALS:
            visible = {
                key: packet[key]
                for key in ("review_item_id", "authority", "source_alias", "source_text")
            }
            envelope = json.dumps(visible, ensure_ascii=False, separators=(",", ":"))
            retry_prompt = (
                ROOT_TEMPLATE.replace("{role}", "ai_primary")
                .replace("{attempt}", "2")
                .replace("{envelope}", envelope)
            )
            expected_length, expected_hash = RETRY_PROMPT_PINS[ordinal]
            retry_bytes = retry_prompt.encode("utf-8")
            if (
                len(retry_bytes) != expected_length
                or hashlib.sha256(retry_bytes).hexdigest() != expected_hash
            ):
                raise ValueError(f"ordinal {ordinal} retry prompt bytes differ")
            attempts.append(
                {
                    "attempt": 2,
                    "task_identity": RETRY_TASKS[ordinal],
                    "prompt": retry_prompt,
                    "final_message": RETRY_FINAL_MESSAGES[ordinal],
                    "outcome": "accepted",
                    "envelope_format": "visible_canonical",
                    "envelope_separator": "space",
                }
            )
        rows.append(
            {
                "release_ordinal": ordinal,
                "review_item_id": packet["review_item_id"],
                "attempts": attempts,
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.packet, args.output)


if __name__ == "__main__":
    main()
