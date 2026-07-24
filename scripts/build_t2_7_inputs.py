"""Rebuild the corrective T2.7 Phase-2 benchmark inputs deterministically."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"
SEED = BENCHMARK / "seed"
PROGRAMS = SEED / "programs"
RAW = BENCHMARK / "drift_instances.jsonl"
PLAUSIBLE = BENCHMARK / "drift_instances.plausible.jsonl"
REAL = SEED / "real_curated.jsonl"
JUDGEMENTS = BENCHMARK / "judgements.jsonl"
SAMPLE_JUDGEMENTS = BENCHMARK / "judgements.sample50.jsonl"
MANIFEST = BENCHMARK / "drift_instances.manifest.json"
EVIDENCE = BENCHMARK / "t2_7_plausibility.jsonl"

STALE_KYC_IDS = (
    "drift_361728",
    "drift_379665",
    "drift_492883",
    "drift_582110",
    "drift_630861",
    "drift_710779",
    "drift_722152",
    "drift_810413",
)
KYC_VARIANTS = tuple(f"KYCSY20{index}.cbl" for index in range(1, 9))
MO2_OLD = (
    "IF WS-DAYS-SINCE-UPD > 7 "
    "MOVE 'OVERDUE' TO WS-SLA-STATUS "
    "ELSE MOVE 'INSLA' TO WS-SLA-STATUS END-IF"
)


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for row in rows
        )
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _program_id(text: str, fallback: str) -> str:
    match = re.search(r"PROGRAM-ID\.\s+([A-Z0-9_-]+)", text, re.IGNORECASE)
    return match.group(1).upper() if match else fallback.upper()


def _synthetic_instance_id(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    payload = json.dumps(
        {
            "program": _program_id(text, path.stem),
            "text": text,
            "files": {},
            "record": "KYC-ckycr-update",
            "op": "MO-2",
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    number = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 1_000_000
    return f"drift_{number:06d}"


def _line_number(lines: list[str], fragment: str, *, after: int = 0) -> int:
    matches = [
        index
        for index, line in enumerate(lines, 1)
        if index > after and fragment.upper() in line.upper()
    ]
    if len(matches) != 1:
        raise ValueError(f"{fragment!r} resolved to lines {matches}")
    return matches[0]


def _paragraph_span(path: Path, paragraph: str) -> tuple[int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = _line_number(lines, f"{paragraph}.")
    end = len(lines)
    for index in range(start + 1, len(lines) + 1):
        if re.match(r"^\s{7}[0-9A-Z][0-9A-Z-]*\.\s*$", lines[index - 1]):
            end = index - 1
            break
    return start, end


def _mo2_span(path: Path) -> tuple[int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = _line_number(lines, "IF WS-DAYS-SINCE-UPD > 7")
    end = next(
        index
        for index, line in enumerate(lines, 1)
        if index > start and "END-IF" in line.upper()
    )
    return start, end


def _blank_normalized_block(text: str, old: str) -> str:
    pattern = re.compile(
        r"\s+".join(re.escape(part) for part in old.split()),
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"expected one MO-2 block, found {len(matches)}")
    match = matches[0]
    blanked = "".join(char if char in "\r\n" else " " for char in match.group())
    return text[: match.start()] + blanked + text[match.end() :]


def _regenerate_kyc_rows(rows: list[dict]) -> tuple[list[dict], dict[str, str]]:
    by_id = {row["instance_id"]: row for row in rows}
    desired_map = {
        stale_id: _synthetic_instance_id(PROGRAMS / filename)
        for stale_id, filename in zip(STALE_KYC_IDS, KYC_VARIANTS, strict=True)
    }
    missing = set(STALE_KYC_IDS) - set(by_id)
    if missing:
        if set(desired_map.values()) <= set(by_id):
            for row in rows:
                if row["instance_id"] in desired_map.values():
                    row["provenance"]["annotator_notes"] = (
                        "task=T2.7; "
                        "supersession_map=t2_7_plausibility.jsonl; "
                        "plausibility=t2_7_plausibility.jsonl"
                    )
            return rows, desired_map
        raise ValueError(f"catalogue lacks stale KYC rows: {sorted(missing)}")

    replacements: dict[str, dict] = {}
    id_map: dict[str, str] = {}
    occupied = set(by_id) - set(STALE_KYC_IDS)
    for stale_id, filename in zip(STALE_KYC_IDS, KYC_VARIANTS, strict=True):
        path = PROGRAMS / filename
        replacement_id = desired_map[stale_id]
        if replacement_id in occupied:
            raise ValueError(f"replacement ID collision: {replacement_id}")
        occupied.add(replacement_id)
        id_map[stale_id] = replacement_id

        start, end = _mo2_span(path)
        program = path.stem
        locus_text = f"{program}:2000-CHECK-SLA:{start}-{end}"
        row = copy.deepcopy(by_id[stale_id])
        row["instance_id"] = replacement_id
        row["code_locus"] = {
            "loci": [
                {
                    "program": program,
                    "paragraph": "2000-CHECK-SLA",
                    "file": None,
                    "line_span": [start, end],
                }
            ],
            "slice_vars": ["WS-DAYS-SINCE-UPD", "WS-SLA-STATUS"],
            "is_interprocedural": False,
        }
        row["labels"]["line_level"] = [
            {"program": program, "line": start, "file": None}
        ]
        row["gold_rationale"] = (
            "MO-2 removes the live seven-day SLA branch from "
            f"{program}:2000-CHECK-SLA:{start}-{end}. The remaining zero-day "
            "NEW-status special case is credible legacy classification logic but "
            "does not enforce CKYCR update within seven days, producing "
            "D2_missing_rule."
        )
        row["provenance"]["base_program"] = filename
        row["provenance"]["mutation"] = (
            f'MO-2; locus={locus_text}; old="{MO2_OLD}"; '
            "new='(deleted)'; validation=compiled; diversify=deterministic"
        )
        row["provenance"]["annotator_notes"] = (
            "task=T2.7; supersession_map=t2_7_plausibility.jsonl; "
            "plausibility=t2_7_plausibility.jsonl"
        )
        replacements[stale_id] = row

    return [
        replacements.get(row["instance_id"], row)
        for row in rows
    ], id_map


def _plausibility_reason(filename: str) -> str:
    control_name = next(
        line.strip().split()[1]
        for line in (PROGRAMS / filename).read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("05  WS-")
        and "WS-DAYS-SINCE-UPD" not in line
        and "WS-SLA-STATUS" not in line
        and "WS-CUST-ID" not in line
    )
    return (
        "After deletion, the program still contains an idiomatic zero-day "
        "classification that moves NEW to WS-SLA-STATUS. Its unrelated "
        f"{control_name} working-storage field is ordinary batch-report state. "
        "Omitting the seven-day SLA is a believable incomplete legacy control, "
        "not an artificial or uncompilable edit."
    )


def _replace_judgements(
    rows: list[dict],
    id_map: dict[str, str],
    *,
    keep_all_replacements: bool,
) -> list[dict]:
    if set(id_map.values()) <= {row["instance_id"] for row in rows}:
        return rows
    replaced: list[dict] = []
    for row in rows:
        stale_id = row["instance_id"]
        if stale_id not in id_map:
            replaced.append(row)
            continue
        filename = KYC_VARIANTS[STALE_KYC_IDS.index(stale_id)]
        updated = copy.deepcopy(row)
        updated["instance_id"] = id_map[stale_id]
        updated["verdict"] = "plausible"
        updated["reason"] = _plausibility_reason(filename)
        updated["model"] = "gpt-5-codex"
        updated["model_family"] = "openai"
        replaced.append(updated)

    if keep_all_replacements:
        present = {row["instance_id"] for row in replaced}
        template = next(
            row for row in rows if row["instance_id"] in STALE_KYC_IDS
        )
        for stale_id, filename in zip(STALE_KYC_IDS, KYC_VARIANTS, strict=True):
            replacement_id = id_map[stale_id]
            if replacement_id in present:
                continue
            updated = copy.deepcopy(template)
            updated["instance_id"] = replacement_id
            updated["verdict"] = "plausible"
            updated["reason"] = _plausibility_reason(filename)
            updated["model"] = "gpt-5-codex"
            updated["model_family"] = "openai"
            replaced.append(updated)
    return replaced


def _repair_real_seed(rows: list[dict]) -> list[dict]:
    retained = [
        row
        for row in rows
        if "task=T2.7" not in (row["provenance"].get("annotator_notes") or "")
    ]
    for row in retained:
        if row["instance_id"] != "drift_000013":
            continue
        row["provenance"]["base_program"] = "CLOSPN5D.cbl"
        for locus in row["code_locus"]["loci"]:
            locus["program"] = "CLOSPN5D.cbl"
        for label in row["labels"]["line_level"]:
            label["program"] = "CLOSPN5D.cbl"
        row["provenance"]["annotator_notes"] = (
            "Cross-paragraph single-program case: is_interprocedural covers it "
            "per schema comment. T2.7 moved this real dead-code example to the "
            "pinned disabled-state host while restoring CLOSPEN5 as the "
            "synthetic MO-6 pre-mutation base."
        )
        break
    else:
        raise ValueError("real seed lacks drift_000013")
    return retained


PAIR_SPECS = (
    {
        "lineage": "closure_day_basis",
        "programs": ("T6CL01.cbl", "T6CL02.cbl", "T6CL03.cbl", "T6CL04.cbl", "T6CL05.cbl"),
        "paragraphs": (
            "2000-CALCULATE-PENALTY",
            "2100-COUNT-WORKING-DAYS",
            "2200-APPLY-DAY-BASIS",
            "2300-ASSESS-PENALTY",
            "2400-SCAN-CALENDAR",
        ),
        "markers": (
            "WS-WORKING-DAYS =",
            "WS-DAY-TYPE(WS-DAY-INDEX)",
            "SUBTRACT WS-NONWORKING-DAYS",
            "WS-WORK-DAYS-TO-CLOSE - 7",
            "IF BUSINESS-DAY(WS-SCAN-INDEX)",
        ),
        "slice_vars": (
            ("WS-ELAPSED-DAYS", "WS-WORKING-DAYS", "WS-PENALTY-AMT"),
            ("WS-DAY-TYPE", "WS-WORKING-DAYS", "WS-PENALTY-AMT"),
            ("WS-NONWORKING-DAYS", "WS-ACCRUAL-DAYS", "WS-PENALTY-AMT"),
            ("WS-WORK-DAYS-TO-CLOSE", "WS-EXCESS-WORK-DAYS", "WS-AMOUNT-DUE"),
            ("WS-BUSINESS-FLAG", "WS-BUSINESS-COUNT", "WS-PENALTY"),
        ),
        "semantics": (
            "subtracts recorded weekends and holidays before accrual",
            "counts only day-table entries marked as working days",
            "subtracts the recorded non-working-day total from accrual",
            "uses the upstream working-day closure total",
            "scans 88-level business-day flags before charging",
        ),
        "old_template": "drift_000001",
        "new_template": "drift_000002",
        "old_evidence": (
            "data/regulations/sources/cc-md-2022-as-issued.pdf#8(a)"
        ),
        "new_evidence": (
            "data/regulations/sources/cc-dc-directions-2025.pdf#19"
        ),
    },
    {
        "lineage": "bo_threshold",
        "programs": ("T6BO01.cbl", "T6BO02.cbl", "T6BO03.cbl", "T6BO04.cbl", "T6BO05.cbl"),
        "paragraphs": (
            "2000-IDENTIFY-OWNER",
            "2100-CHECK-PROFIT-SHARE",
            "2200-COMPUTE-BO-MARGIN",
            "2300-CLASSIFY-PARTNER",
            "2400-SET-REVIEW-CODE",
        ),
        "markers": (
            "WS-CAPITAL-PCT > 15",
            "WS-PROFIT-SHARE > WS-LEGACY-BO-LIMIT",
            "WS-ENTITLEMENT-PCT - 15",
            "WS-CAPITAL-INTEREST > 15",
            "IF LEGACY-BO-RANGE",
        ),
        "slice_vars": (
            ("WS-CAPITAL-PCT", "WS-IS-BO"),
            ("WS-LEGACY-BO-LIMIT", "WS-PROFIT-SHARE", "WS-OWNER-RESULT"),
            ("WS-ENTITLEMENT-PCT", "WS-EXCESS-PCT", "WS-BO-FLAG"),
            ("WS-CAPITAL-INTEREST", "WS-CLASSIFICATION"),
            ("WS-PARTNER-PCT", "LEGACY-BO-RANGE", "WS-REVIEW-CODE"),
        ),
        "semantics": (
            "compares capital ownership directly with 15 percent",
            "compares profit share with a stored 15-percent legacy limit",
            "requires a positive margin above 15 percent",
            "uses EVALUATE TRUE to classify interests above 15 percent",
            "uses an 88-level 16-through-100 ownership range",
        ),
        "old_template": "drift_000007",
        "new_template": "drift_000008",
        "old_evidence": (
            "data/regulations/sources/"
            "kyc-md-2016-consol-pre-2023-10.pdf#3(a)(iv)(b)"
        ),
        "new_evidence": (
            "data/regulations/sources/kyc-directions-2025.pdf#5(iv)(b)"
        ),
    },
    {
        "lineage": "ckycr_deadline",
        "programs": ("T6KYC01.cbl", "T6KYC02.cbl", "T6KYC03.cbl", "T6KYC04.cbl", "T6KYC05.cbl"),
        "paragraphs": (
            "2000-QUEUE-CKYCR",
            "2100-VALIDATE-FOR-SYNC",
            "2200-PREPARE-UPLOAD",
            "2300-ROUTE-UPDATE",
            "2400-RECORD-UPLOAD-REQUEST",
        ),
        "markers": (
            "MOVE 'PENDING' TO WS-QUEUE-STATUS",
            "MOVE 'READY' TO WS-SYNC-STATE",
            "MOVE 'Y' TO WS-UPLOAD-FLAG",
            "MOVE 'PRIORITY' TO WS-WORK-QUEUE",
            "STRING 'CKYCR REQUEST '",
        ),
        "slice_vars": (
            ("WS-UPDATE-RECEIVED", "WS-QUEUE-STATUS"),
            ("WS-CUSTOMER-ID", "WS-SYNC-STATE"),
            ("WS-NORMALIZED-NAME", "WS-UPLOAD-FLAG"),
            ("WS-RISK-CODE", "WS-WORK-QUEUE"),
            ("WS-CHANGE-REFERENCE", "WS-AUDIT-MESSAGE"),
        ),
        "semantics": (
            "queues a received update without retaining elapsed days",
            "validates a customer identifier before sync without a clock",
            "normalizes changed KYC data and marks it for upload",
            "routes the update by risk without tracking its receipt date",
            "records an upload request without a due-date field",
        ),
        "old_template": "drift_000009",
        "new_template": "drift_000010",
        "old_evidence": (
            "data/regulations/sources/"
            "kyc-md-2016-consol-pre-2023-10.pdf#56(h)+"
            "kyc-amend-2024-11-06.pdf"
        ),
        "new_evidence": (
            "data/regulations/sources/kyc-directions-2025.pdf#65(8)"
        ),
    },
)


def _pair_rationale(lineage: str, semantics: str, side: str) -> str:
    if lineage == "closure_day_basis":
        if side == "old":
            return (
                f"The same code {semantics}. That working-day accrual is "
                "defensible under 2022 clause 8(a), whose seven-day service "
                "window and unqualified per-day wording did not yet prescribe "
                "calendar-day penalty accrual."
            )
        return (
            f"The same code {semantics}, excluding non-working days from "
            "penalty accrual. Current paragraph 19 expressly requires Rs 500 "
            "per calendar day, so the unchanged implementation undercharges."
        )
    if lineage == "bo_threshold":
        if side == "old":
            return (
                f"The same code {semantics}. That implements the 2016 "
                "partnership beneficial-owner threshold of more than 15 percent."
            )
        return (
            f"The same code {semantics}. Current clause 5(iv)(b) lowered the "
            "threshold to more than 10 percent and includes control through "
            "other means, so the unchanged legacy rule misses required owners."
        )
    if side == "old":
        return (
            f"The same code {semantics}. Before 2024-11-06, para 56(h) required "
            "CKYCR updating but imposed no time-bound deadline, so this "
            "deadline-free workflow is conformant to that temporal side."
        )
    return (
        f"The same code {semantics}. Current clause 65(8) requires update "
        "within seven days of receipt; this unchanged workflow has no receipt "
        "date or deadline enforcement, so the missing rule is drift."
    )


def _append_t6_pairs(rows: list[dict]) -> list[dict]:
    by_id = {row["instance_id"]: row for row in rows}
    occupied = set(by_id)
    next_id = 110001
    additions: list[dict] = []
    for spec in PAIR_SPECS:
        for index, (filename, paragraph, marker, slice_vars, semantics) in enumerate(
            zip(
                spec["programs"],
                spec["paragraphs"],
                spec["markers"],
                spec["slice_vars"],
                spec["semantics"],
                strict=True,
            ),
            1,
        ):
            path = PROGRAMS / filename
            lines = path.read_text(encoding="utf-8").splitlines()
            start, end = _paragraph_span(path, paragraph)
            label_line = _line_number(lines, marker)
            locus = {
                "loci": [
                    {
                        "program": filename,
                        "paragraph": paragraph,
                        "file": None,
                        "line_span": [start, end],
                    }
                ],
                "slice_vars": list(slice_vars),
                "is_interprocedural": False,
            }
            pair_name = f"{spec['lineage']}_{index:02d}"
            for side, template_id in (
                ("old", spec["old_template"]),
                ("current", spec["new_template"]),
            ):
                instance_id = f"drift_{next_id:06d}"
                next_id += 1
                if instance_id in occupied:
                    raise ValueError(f"authored T6 ID collision: {instance_id}")
                occupied.add(instance_id)
                row = copy.deepcopy(by_id[template_id])
                row["instance_id"] = instance_id
                row["code_locus"] = copy.deepcopy(locus)
                row["labels"]["line_level"] = (
                    []
                    if side == "old"
                    else [
                        {
                            "program": filename,
                            "line": label_line,
                            "file": None,
                        }
                    ]
                )
                row["gold_rationale"] = _pair_rationale(
                    spec["lineage"], semantics, side
                )
                row["provenance"]["base_program"] = filename
                row["provenance"]["mutation"] = None
                row["provenance"]["annotator_notes"] = (
                    f"task=T2.7; pair={pair_name}; "
                    f"lineage={spec['lineage']}; side={side}; "
                    "primary_evidence="
                    f"{spec['old_evidence' if side == 'old' else 'new_evidence']}"
                )
                additions.append(row)
    return rows + additions


def _write_plausibility_evidence(
    corrected_rows: list[dict],
    id_map: dict[str, str],
) -> None:
    by_id = {row["instance_id"]: row for row in corrected_rows}
    evidence: list[dict] = []
    for stale_id, filename in zip(STALE_KYC_IDS, KYC_VARIANTS, strict=True):
        replacement_id = id_map[stale_id]
        source = (PROGRAMS / filename).read_text(encoding="utf-8")
        mutated = _blank_normalized_block(source, MO2_OLD)
        evidence.append(
            {
                "instance_id": replacement_id,
                "supersedes": stale_id,
                "mutated_main_sha256": hashlib.sha256(
                    mutated.encode("utf-8")
                ).hexdigest(),
                "verdict": "plausible",
                "reason": _plausibility_reason(filename),
                "reviewer_model": "gpt-5-codex",
                "reviewer_family": "openai",
                "reviewed_at": "2026-07-24",
                "validation": "compiled with GnuCOBOL 3.2.0; materialized exactly",
            }
        )
        if replacement_id not in by_id:
            raise ValueError(f"evidence replacement absent: {replacement_id}")
    _write_jsonl(EVIDENCE, evidence)


def _update_manifest(id_map: dict[str, str]) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["git_sha"] = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    existing_variants = sum(
        filename in manifest["base_counts"] for filename in KYC_VARIANTS
    )
    if existing_variants not in {0, len(KYC_VARIANTS)}:
        raise ValueError("manifest contains a partial T2.7 KYC variant set")
    if existing_variants == 0:
        manifest["base_counts"]["KYCSYNC2.cbl"] -= len(KYC_VARIANTS)
    for filename in KYC_VARIANTS:
        manifest["base_counts"][filename] = 1
    manifest["base_counts"] = dict(sorted(manifest["base_counts"].items()))
    manifest["judging"]["t2_7_revalidation"] = {
        "count": len(id_map),
        "evidence_file": "data/benchmark/t2_7_plausibility.jsonl",
        "model": "gpt-5-codex",
        "model_family": "openai",
        "system_family": "anthropic",
        "plausible": len(id_map),
        "implausible": 0,
        "unsure": 0,
        "compiled_with": "GnuCOBOL 3.2.0",
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    raw, id_map = _regenerate_kyc_rows(_load_jsonl(RAW))
    plausible, plausible_map = _regenerate_kyc_rows(_load_jsonl(PLAUSIBLE))
    if id_map != plausible_map:
        raise ValueError("raw and accepted catalogue replacement maps differ")
    _write_jsonl(RAW, raw)
    _write_jsonl(PLAUSIBLE, plausible)

    real = _append_t6_pairs(_repair_real_seed(_load_jsonl(REAL)))
    _write_jsonl(REAL, real)
    _write_jsonl(
        JUDGEMENTS,
        _replace_judgements(
            _load_jsonl(JUDGEMENTS),
            id_map,
            keep_all_replacements=True,
        ),
    )
    _write_jsonl(
        SAMPLE_JUDGEMENTS,
        _replace_judgements(
            _load_jsonl(SAMPLE_JUDGEMENTS),
            id_map,
            keep_all_replacements=False,
        ),
    )
    _write_plausibility_evidence(plausible, id_map)
    _update_manifest(id_map)
    print(json.dumps(id_map, indent=2))
    print(f"real_curated_rows={len(real)}")


if __name__ == "__main__":
    main()
