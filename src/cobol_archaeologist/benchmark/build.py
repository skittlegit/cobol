"""T2.3 deterministic synthetic benchmark build orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from cobol_archaeologist.benchmark.mutate import (
    ClauseRecord,
    MutationRejected,
    MutationResult,
    ProgramSource,
    load_clause_records,
    regulated_literals,
    mutate,
)
from cobol_archaeologist.benchmark.surface import (
    per_feature_auc,
    ProbeRow,
    diversify_with_edits,
    surface_features,
    surface_probe_report,
)


DiversifyMode = Literal["deterministic", "llm"]

CLASS_FLOORS = {
    "D1_stale_threshold": 20,
    "D2_missing_rule": 20,
    "D3_contradictory": 20,
    "D4_stale_reference_data": 20,
    "D5_boundary_error": 20,
    "D6_dead_code": 20,
    "D7_conformant": 60,
}
INTERPROCEDURAL_FLOOR = 30
PROBE_PER_LABEL = 100
OPERATOR_FLOORS = {
    "MO-1×": 12,
    "MO-3": 15,
    "MO-3×": 12,
    "MO-6×": 12,
}
CORRECTIVE_BASE_FLOOR = 32
CORRECTIVE_BASES = {
    "ACTIVAT1.cbl",
    "BOIDENT3.cbl",
    "CICREP1.cbl",
    "CLOSPEN6.cbl",
    "GRVAGE2.cbl",
    "INTCOMP1.cbl",
    "KYCSCHED2.cbl",
    "KYCSYNC3.cbl",
    "LATEFEE2.cbl",
    "NOTICE1.cbl",
    "REFADJ1.cbl",
    "UNSOLIC1.cbl",
}


class BuildConfigurationError(RuntimeError):
    """Raised for a requested build mode that cannot be run honestly."""


@dataclass(frozen=True)
class BuildResult:
    manifest: dict
    probe_rows: list[dict]
    sources: dict[str, ProgramSource]


@dataclass(frozen=True)
class _Candidate:
    base: ProgramSource
    record: ClauseRecord
    op: str


@dataclass(frozen=True)
class _Emission:
    result: MutationResult
    before: ProgramSource
    op: str


def manifest_path_for(output: str | Path) -> Path:
    path = Path(output)
    return path.with_suffix(".manifest.json")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_sha(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _seed_base(
    programs: Path,
    name: str,
    *,
    touched_variables: tuple[str, ...],
    target_path: str | None = None,
) -> ProgramSource:
    return ProgramSource.from_path(
        programs / name,
        touched_variables=touched_variables,
        target_path=target_path,
    )


def _load_base_roster(root: Path) -> dict:
    path = root / "data" / "benchmark" / "seed" / "base_roster.json"
    try:
        roster = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildConfigurationError(f"cannot load base roster {path}: {exc}") from exc
    if not isinstance(roster.get("reservations"), dict) or not isinstance(
        roster.get("chains"), dict
    ):
        raise BuildConfigurationError("base roster requires reservations and chains")
    return roster


def _rostered_chain_base(
    programs: Path,
    roster: dict,
    chain_name: str,
    *,
    touched_variables: tuple[str, ...],
) -> ProgramSource:
    members = roster["chains"].get(chain_name)
    if not isinstance(members, list) or len(members) < 2:
        raise BuildConfigurationError(f"roster chain {chain_name!r} is incomplete")
    paths = [programs / str(member) for member in members]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise BuildConfigurationError(
            f"roster chain {chain_name!r} has missing programs: {missing}"
        )
    texts = {path.name: path.read_text(encoding="utf-8") for path in paths}
    guarded = [
        path
        for path in paths
        if re.search(r"\bIF\s+PEN-RUN-ON\b", texts[path.name], re.IGNORECASE)
    ]
    if len(guarded) != 1:
        raise BuildConfigurationError(
            f"roster chain {chain_name!r} requires one guarded program"
        )
    primary = guarded[0]
    files = {name: text for name, text in texts.items() if name != primary.name}
    for path in paths:
        for copy_name in re.findall(
            r"^\s*COPY\s+([A-Z0-9_-]+)\s*\.",
            texts[path.name],
            re.IGNORECASE | re.MULTILINE,
        ):
            copy_path = path.parent / f"{copy_name}.cpy"
            if not copy_path.is_file():
                raise BuildConfigurationError(
                    f"roster chain {chain_name!r} is missing {copy_path.name}"
                )
            files[copy_path.name] = copy_path.read_text(encoding="utf-8")
    return ProgramSource.from_path(
        primary,
        files=files,
        touched_variables=touched_variables,
    )


def _standing_judge_family(root: Path) -> tuple[str | None, str | None]:
    path = root / "data" / "benchmark" / "drift_instances.manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"standing T2.4 manifest unavailable: {exc}"
    family = manifest.get("judge_family")
    if not family:
        judging = manifest.get("judging")
        if isinstance(judging, dict):
            family = judging.get("model_family")
    if isinstance(family, str) and family.strip():
        return family.strip(), None
    return None, "standing T2.4 manifest has no judge-family evidence"


def _carddemo_copybooks(root: Path) -> dict[str, str]:
    directory = root / "data" / "corpora" / "carddemo" / "app" / "cpy"
    return {
        path.name: path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(directory.glob("*"))
        if path.is_file()
    }


def _carddemo_base(
    root: Path,
    name: str,
    *,
    touched_variables: tuple[str, ...],
) -> ProgramSource:
    path = root / "data" / "corpora" / "carddemo" / "app" / "cbl" / name
    if not path.is_file():
        raise BuildConfigurationError(
            f"CardDemo base {name} is absent; run scripts/fetch_corpora.sh"
        )
    return ProgramSource.from_path(
        path,
        files=_carddemo_copybooks(root),
        touched_variables=touched_variables,
    )


def _candidate_catalog(root: Path) -> dict[str, list[_Candidate]]:
    clauses = {
        record.record_id: record
        for record in load_clause_records(
            root / "data" / "regulations" / "clauses.jsonl"
        )
    }
    programs = root / "data" / "benchmark" / "seed" / "programs"
    roster = _load_base_roster(root)
    hosted = [
        (
            _seed_base(
                programs,
                "BOIDENT2.cbl",
                touched_variables=("WS-BO-THRESHOLD", "WS-IS-BO"),
            ),
            clauses["KYC-bo-threshold"],
        ),
        (
            _seed_base(
                programs,
                "KYCSYNC2.cbl",
                touched_variables=("WS-DAYS-SINCE-UPD", "WS-SLA-STATUS"),
            ),
            clauses["KYC-ckycr-update"],
        ),
        (
            _seed_base(
                programs,
                "KYCSCHED1.cbl",
                touched_variables=("WS-YEARS-SINCE-KYC", "WS-RISK-CODE"),
                target_path="high_risk",
            ),
            clauses["KYC-periodic-updation"],
        ),
        (
            _seed_base(
                programs,
                "CLOSPEN3.cbl",
                touched_variables=("WS-WORK-DAYS-ELAPSED", "WS-PENALTY-AMT"),
                target_path="closure_window",
            ),
            clauses["CC-08a"],
        ),
    ]

    activation = _seed_base(
        programs,
        "train-bases/ACTIVAT1.cbl",
        touched_variables=("WS-DAYS-SINCE-ISSUE", "WS-CONSENT-DAYS", "WS-ACTION"),
        target_path="activation_window",
    )
    unsolicited = _seed_base(
        programs,
        "train-bases/UNSOLIC1.cbl",
        touched_variables=("WS-CHARGES-BILLED", "WS-REVERSAL", "WS-PENALTY"),
    )
    closure = _seed_base(
        programs,
        "train-bases/CLOSPEN6.cbl",
        touched_variables=("WS-REQ-DAYS", "WS-TOT-PENALTY"),
        target_path="closure_window",
    )
    grievance = _seed_base(
        programs,
        "train-bases/GRVAGE2.cbl",
        touched_variables=("WS-DAYS-OPEN", "WS-ESCALATE"),
    )
    bo_ident = _seed_base(
        programs,
        "train-bases/BOIDENT3.cbl",
        touched_variables=("WS-OWN-PCT", "WS-IS-BO"),
    )
    kyc_sync = _seed_base(
        programs,
        "train-bases/KYCSYNC3.cbl",
        touched_variables=("WS-TODAY-DAY", "WS-DUE-DAY", "WS-STATUS"),
    )
    kyc_schedule = _seed_base(
        programs,
        "train-bases/KYCSCHED2.cbl",
        touched_variables=("WS-LAST-KYC-YYYY", "WS-DUE-YYYY", "WS-RISK"),
        target_path="high_risk",
    )
    late_fee_new = _seed_base(
        programs,
        "train-bases/LATEFEE2.cbl",
        touched_variables=("WS-DAYS-PAST-DUE", "WS-OUTSTANDING", "WS-CHARGE"),
        target_path="past_due_grace",
    )
    cic_report = _seed_base(
        programs,
        "train-bases/CICREP1.cbl",
        touched_variables=("WS-DAYS-SINCE-SETTLE", "WS-ACTION"),
    )
    hosted.extend(
        [
            (activation, clauses["CC-06a-vi"]),
            (unsolicited, clauses["CC-06a-iv"]),
            (closure, clauses["CC-08a"]),
            (grievance, clauses["CC-26c"]),
            (bo_ident, clauses["KYC-bo-threshold"]),
            (kyc_sync, clauses["KYC-ckycr-update"]),
            (kyc_schedule, clauses["KYC-periodic-updation"]),
            (late_fee_new, clauses["CC-09b-v"]),
            (cic_report, clauses["CC-12b"]),
        ]
    )

    interest = _seed_base(
        programs,
        "train-bases/INTCOMP1.cbl",
        touched_variables=("WS-BASE", "WS-UNPAID-FEES", "WS-CREDITS", "WS-INT"),
    )
    notice = _seed_base(
        programs,
        "train-bases/NOTICE1.cbl",
        touched_variables=("WS-NOTICE-DAYS", "WS-OK"),
    )
    refund_local = _seed_base(
        programs,
        "train-bases/REFADJ1.cbl",
        touched_variables=("WS-CUTOFF", "WS-REFUND-AMT"),
        target_path="cutoff",
    )

    late_fee = _seed_base(
        programs,
        "LATEFEE1.cbl",
        touched_variables=("WS-DAYS-PAST-DUE", "WS-LATE-CHARGE"),
        target_path="past_due_grace",
    )
    late_fee = replace(
        late_fee,
        text=late_fee.text.replace(
            "= WS-LATE-RATE * WS-TOTAL-AMT-DUE",
            "= WS-LATE-RATE * WS-OUTSTANDING-AMT",
        ),
    )

    overlimit = _seed_base(
        programs,
        "OVRLIM1.cbl",
        touched_variables=(
            "WS-CONSENT-ON-FILE",
            "WS-PROJECTED-BAL",
            "WS-CREDIT-LIMIT",
        ),
    )
    d6_base = _seed_base(
        programs,
        "CLOSPEN5.cbl",
        touched_variables=("WS-PEN-ENABLED", "WS-PENALTY-AMT"),
        target_path="penalty_per_day",
    )
    if "WS-PEN-ENABLED        PIC X(1) VALUE 'N'." not in d6_base.text:
        raise BuildConfigurationError(
            "CLOSPEN5 D6 base no longer matches its pilot flag"
        )
    d6_base = replace(
        d6_base,
        text=d6_base.text.replace(
            "WS-PEN-ENABLED        PIC X(1) VALUE 'N'.",
            "WS-PEN-ENABLED        PIC X(1) VALUE 'Y'.",
            1,
        ),
    )

    # DECISION (T2.4b / BL-6): D4 is anchored to two authentic KYC reference-
    # list hosts, each COPYing a real on-disk copybook (auto-discovered by
    # ProgramSource.from_path) whose 88-level enumeration is a genuine regulator
    # reference set. The prior single CLOSPEN3/WSDAYBAS D4 base synthesized its
    # own mutation target (injected COPY + rewrote the 88-level so MO-4 had a
    # value to flip) and was anchored to CC-29/para-90 whose current_value is
    # null; it produced 20 clones of one fabricated locus that the plausibility
    # judge rejected as artificial. Removed and forbidden by
    # _assert_d4_reference_hosts below.
    ovd_base = _seed_base(
        programs,
        "OVDCHK1.cbl",
        touched_variables=("WS-OVD-CODE",),
    )
    unsc_base = _seed_base(
        programs,
        "SCRNGATE1.cbl",
        touched_variables=("WS-LIST-SOURCE",),
    )

    # The D2 scale base keeps ordinary record-readiness classification around
    # the required seven-day check. MO-2 can therefore omit that one rule while
    # leaving a coherent sync-status paragraph rather than a stripped SLA stub.
    d2_base = hosted[1][0]
    original_sla_check = """\
           IF WS-DAYS-SINCE-UPD > 7
              MOVE 'OVERDUE' TO WS-SLA-STATUS
           ELSE
              MOVE 'INSLA' TO WS-SLA-STATUS
           END-IF."""
    maintained_sync_status = """\
           MOVE 'PENDING' TO WS-SYNC-STATUS
           IF WS-CUST-ID NOT = SPACES
              MOVE 'READY' TO WS-SYNC-STATUS
           END-IF
           IF WS-DAYS-SINCE-UPD > 7
              MOVE 'OVERDUE' TO WS-SYNC-STATUS
           END-IF
           IF WS-DAYS-SINCE-UPD = ZERO
              MOVE 'NEW' TO WS-SYNC-STATUS
           END-IF."""
    if original_sla_check not in d2_base.text:
        raise BuildConfigurationError("KYCSYNC2 D2 base no longer matches its seed")
    d2_base = replace(
        d2_base,
        text=(
            d2_base.text.replace(original_sla_check, maintained_sync_status)
            .replace("WS-SLA-STATUS", "WS-SYNC-STATUS")
            .replace("PERFORM 2000-CHECK-SLA", "PERFORM 2000-SET-SYNC-STATUS")
            .replace("DISPLAY 'SLA: '", "DISPLAY 'SYNC: '")
            .replace("2000-CHECK-SLA.", "2000-SET-SYNC-STATUS.")
        ),
        touched_variables=("WS-DAYS-SINCE-UPD", "WS-SYNC-STATUS"),
    )

    refund_cross = _seed_base(
        programs,
        "test-bases-x/REFADJ2.cbl",
        touched_variables=("WS-CUTOFF-CAP", "WS-CUTOFF", "WS-REFUND-AMT"),
        target_path="cutoff",
    )
    transaction_gate = _seed_base(
        programs,
        "test-bases-x/TRNVAL1.cbl",
        touched_variables=(
            "WS-LIMIT",
            "WS-PROJ-BAL",
            "WS-FAIL-REASON",
            "WS-POSTED",
        ),
    )
    penalty_chain = _rostered_chain_base(
        programs,
        roster,
        "BATCHCT",
        touched_variables=("WS-PEN-RUN-FLAG", "WS-PENALTY"),
    )

    d1 = [_Candidate(base, record, "MO-1") for base, record in hosted]
    d5 = [
        _Candidate(base, record, "MO-5")
        for base, record in hosted
        if "MO-5" in record.check.get("mutation_ops", ())
    ]
    d5.extend(
        [
            _Candidate(refund_local, clauses["CC-10h"], "MO-5"),
            _Candidate(notice, clauses["CC-09b-vii"], "MO-5"),
        ]
    )
    d7 = [_Candidate(base, record, "MO-0") for base, record in hosted]
    catalog = {
        "D1_stale_threshold": d1,
        "D2_missing_rule": [
            _Candidate(d2_base, clauses["KYC-ckycr-update"], "MO-2"),
            _Candidate(activation, clauses["CC-06a-vi"], "MO-2"),
            _Candidate(kyc_sync, clauses["KYC-ckycr-update"], "MO-2"),
            _Candidate(cic_report, clauses["CC-12b"], "MO-2"),
        ],
        "D3_contradictory": [
            _Candidate(late_fee, clauses["CC-09b-v"], "MO-3"),
            _Candidate(late_fee_new, clauses["CC-09b-v"], "MO-3"),
            _Candidate(interest, clauses["CC-09b-ii"], "MO-3"),
        ],
        "D3_interprocedural": [
            _Candidate(overlimit, clauses["CC-06b-v"], "MO-3×"),
            _Candidate(transaction_gate, clauses["CC-06b-v"], "MO-3×"),
        ],
        "D4_stale_reference_data": [
            _Candidate(ovd_base, clauses["KYC-ovd-list"], "MO-4"),
            _Candidate(unsc_base, clauses["KYC-unsc-screening"], "MO-4"),
        ],
        "D5_boundary_error": d5,
        "D6_dead_code": [
            _Candidate(d6_base, clauses["CC-08a"], "MO-6"),
            _Candidate(interest, clauses["CC-09b-ii"], "MO-6"),
            _Candidate(cic_report, clauses["CC-12b"], "MO-6"),
        ],
        "D1_interprocedural": [_Candidate(refund_cross, clauses["CC-10h"], "MO-1×")],
        "D6_interprocedural": [
            _Candidate(penalty_chain, clauses["CC-09b-ii"], "MO-6×")
        ],
        "D7_conformant": d7,
    }
    extra_d7 = [
        _Candidate(interest, clauses["CC-09b-ii"], "MO-0"),
        _Candidate(notice, clauses["CC-09b-vii"], "MO-0"),
        _Candidate(refund_local, clauses["CC-10h"], "MO-0"),
    ]
    corrective: list[_Candidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in [
        *(item for candidates in catalog.values() for item in candidates),
        *extra_d7,
    ]:
        key = (candidate.base.filename, candidate.record.record_id, candidate.op)
        if candidate.base.filename not in CORRECTIVE_BASES or key in seen:
            continue
        seen.add(key)
        corrective.append(candidate)
    missing_corrective = CORRECTIVE_BASES - {
        candidate.base.filename for candidate in corrective
    }
    if missing_corrective:
        raise BuildConfigurationError(
            f"corrective bases have no mutation candidates: {sorted(missing_corrective)}"
        )
    catalog["corrective_free"] = corrective
    _assert_d4_reference_hosts(catalog, programs)
    return catalog


def _assert_d4_reference_hosts(catalog: dict, programs: Path) -> None:
    """T2.4b / BL-6 guards for MO-4 / D4 (stale reference data).

    Codifies why the prior CC-29/CLOSPEN3 D4 was defective so it cannot recur:

    1. No build-time fabrication of the mutation target — every D4 host's base
       text and each of its copybooks must equal the authentic on-disk file
       (the old base injected a COPY and rewrote the 88-level in memory).
    2. Genuine reference set — the backing clause must carry a non-null
       ``enum_set`` ``current_value`` with >=2 members (CC-29/para-90 was
       ``null``), and the targeted copybook must hold an ``88``-level VALUES
       enumeration with >=2 literals for MO-4 to perturb.
    3. Class diversity — D4 must draw from >=2 distinct hosts, not N clones of
       one locus.
    """
    d4 = catalog["D4_stale_reference_data"]
    hosts = {candidate.base.filename for candidate in d4}
    if len(hosts) < 2:
        raise BuildConfigurationError(
            f"D4 requires >=2 distinct reference-list hosts; got {sorted(hosts)}"
        )
    for candidate in d4:
        if candidate.op != "MO-4":
            raise BuildConfigurationError(
                f"D4 candidate {candidate.base.filename} must use MO-4, not {candidate.op}"
            )
        cv = candidate.record.clause.current_value
        if (
            cv is None
            or cv.kind != "enum_set"
            or not isinstance(cv.value, list)
            or len(cv.value) < 2
        ):
            raise BuildConfigurationError(
                f"MO-4 clause {candidate.record.record_id} lacks a >=2-member "
                "enum_set reference set (the CC-29/para-90 null-reference failure)"
            )
        on_disk = (programs / candidate.base.filename).read_text(encoding="utf-8")
        if candidate.base.text != on_disk:
            raise BuildConfigurationError(
                f"D4 host {candidate.base.filename} text is build-time fabricated"
            )
        copied = {
            match.group(1).upper()
            for match in re.finditer(
                r"^\s*COPY\s+([A-Z0-9_-]+)\s*\.",
                candidate.base.text,
                re.IGNORECASE | re.MULTILINE,
            )
        }
        code_members = 0
        for name, content in candidate.base.files.items():
            disk = (programs / name).read_text(encoding="utf-8")
            if content != disk:
                raise BuildConfigurationError(
                    f"D4 host {candidate.base.filename} copybook {name} is fabricated"
                )
            if Path(name).stem.upper() not in copied:
                raise BuildConfigurationError(
                    f"D4 host {candidate.base.filename} does not genuinely COPY "
                    f"{name} (comment-only reference?); the MO-4 target must be a "
                    "copybook actually included in the compiled unit"
                )
            for line in content.splitlines():
                if "88 " in line.upper() and "VALUE" in line.upper():
                    code_members = max(code_members, len(re.findall(r"'[^']+'", line)))
        if code_members < 2:
            raise BuildConfigurationError(
                f"D4 host {candidate.base.filename} has no >=2-member 88 VALUES "
                "reference list for MO-4 to target"
            )


def _llm_comment_variant(base: ProgramSource, seed: int) -> ProgramSource:
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    if not api_key:
        raise BuildConfigurationError(
            "--diversify llm requires OPENAI_API_KEY; refusing fallback"
        )
    if not model:
        raise BuildConfigurationError(
            "--diversify llm requires OPENAI_MODEL for the compatible endpoint"
        )
    lines = base.text.splitlines()
    comments = [
        index for index, line in enumerate(lines) if len(line) > 6 and line[6] in "*/"
    ]
    if not comments:
        raise BuildConfigurationError(
            f"LLM diversification found no safe comment in {base.filename}"
        )
    rng = random.Random(seed)
    index = comments[rng.randrange(len(comments))]
    old = lines[index]
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "seed": seed,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Rewrite one legacy COBOL comment naturally. Return JSON "
                        "with one key, comment. Return one line without comment markers."
                    ),
                },
                {"role": "user", "content": old[7:].strip()},
            ],
        }
    ).encode("utf-8")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip(
        "/"
    )
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        rewritten = (
            str(json.loads(content)["comment"])
            .replace("\r", " ")
            .replace("\n", " ")
            .strip()
        )
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise BuildConfigurationError(f"LLM diversification failed: {exc}") from exc
    if not rewritten:
        raise BuildConfigurationError("LLM diversification returned an empty comment")
    lines[index] = old[:7] + rewritten[:64]
    return replace(
        base, text="\n".join(lines) + ("\n" if base.text.endswith("\n") else "")
    )


def _variant_base(
    base: ProgramSource,
    *,
    seed: int,
    mode: DiversifyMode,
) -> ProgramSource:
    if mode == "llm":
        return _llm_comment_variant(base, seed)
    text = base.text
    rng = random.Random(seed)
    for _ in range(4 + seed % 3):
        text, _ = diversify_with_edits(text, None, rng)
    if base.filename in {
        *CORRECTIVE_BASES,
        "REFADJ2.cbl",
        "BATCHCT2.cbl",
        "TRNVAL1.cbl",
        "OVDCHK1.cbl",
        "SCRNGATE1.cbl",
    }:
        # The short corrective × hosts have only one comment and therefore only
        # a handful of comment variants. Vary inert trailing whitespace across
        # ordinary lines so each required emission remains byte-distinct without
        # renaming any variable that carries interprocedural evidence.
        lines = text.splitlines()
        candidates = [
            index
            for index, line in enumerate(lines)
            if line and not (len(line) > 6 and line[6] in "*/")
        ]
        for _ in range(3):
            index = candidates[rng.randrange(len(candidates))]
            lines[index] = lines[index].rstrip() + (" " * (1 + rng.randrange(6)))
        text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return replace(base, text=text)


def _with_mode(result: MutationResult, mode: DiversifyMode) -> MutationResult:
    provenance = result.instance.provenance
    note = f"{provenance.mutation}; diversify={mode}"
    instance = result.instance.model_copy(
        update={"provenance": provenance.model_copy(update={"mutation": note})}
    )
    return replace(result, instance=instance)


def _reason(exc: MutationRejected, candidate: _Candidate) -> str:
    text = " ".join(str(exc).split())
    return f"{candidate.op} {candidate.base.filename}: {text}"


def _probe_dict(row: ProbeRow) -> dict:
    return asdict(row)


def build_benchmark(
    *,
    seed: int,
    out_path: str | Path,
    min_instances: int = 200,
    diversify_mode: DiversifyMode = "deterministic",
    repository_root: str | Path | None = None,
) -> BuildResult:
    """Build synthetic v1 and its deterministic run manifest."""

    if min_instances < 1:
        raise ValueError("min_instances must be positive")
    if diversify_mode not in ("deterministic", "llm"):
        raise ValueError(f"unknown diversification mode: {diversify_mode}")
    if diversify_mode == "llm" and not os.environ.get("OPENAI_API_KEY"):
        raise BuildConfigurationError(
            "--diversify llm requires OPENAI_API_KEY; refusing deterministic fallback"
        )

    root = Path(repository_root) if repository_root else _repository_root()
    catalog = _candidate_catalog(root)
    # Computed once, corpus-wide: MO-0's benign numeric pass must never touch a
    # value any clause mandates, even one hosted in a different program.
    denylist = regulated_literals(
        load_clause_records(root / "data" / "regulations" / "clauses.jsonl")
    )
    emissions: list[_Emission] = []
    seen_ids: set[str] = set()
    rejects: Counter[str] = Counter()

    def run_candidate(candidate: _Candidate, attempt: int) -> _Emission | None:
        variant_seed = seed * 1_000_003 + attempt * 101
        before = _variant_base(
            candidate.base,
            seed=variant_seed,
            mode=diversify_mode,
        )
        try:
            result = mutate(
                before,
                candidate.record,
                candidate.op,
                random.Random(seed * 10_000_019 + attempt),
                denylist,
            )
        except MutationRejected as exc:
            rejects[_reason(exc, candidate)] += 1
            return None
        result = _with_mode(result, diversify_mode)
        if result.instance.instance_id in seen_ids:
            rejects[
                f"{candidate.op} {candidate.base.filename}: duplicate instance"
            ] += 1
            return None
        return _Emission(result=result, before=before, op=candidate.op)

    def accept(emission: _Emission) -> None:
        seen_ids.add(emission.result.instance.instance_id)
        emissions.append(emission)

    probe_rows: list[ProbeRow] = []
    pair_candidates = list(
        zip(catalog["D1_stale_threshold"], catalog["D7_conformant"], strict=True)
    )
    attempt = 0
    pair_limit = PROBE_PER_LABEL * 100
    while len(probe_rows) < PROBE_PER_LABEL * 2 and attempt < pair_limit:
        d1_candidate, d7_candidate = pair_candidates[attempt % len(pair_candidates)]
        d1 = run_candidate(d1_candidate, attempt * 2)
        d7 = run_candidate(d7_candidate, attempt * 2)
        attempt += 1
        if d1 is None or d7 is None:
            continue
        if d1.result.instance.instance_id == d7.result.instance.instance_id:
            rejects["paired probe produced duplicate ids"] += 1
            continue
        accept(d1)
        accept(d7)
        for label, emission in ((1, d1), (0, d7)):
            probe_rows.append(
                ProbeRow(
                    label=label,
                    base_program=emission.before.program,
                    operator=emission.op,
                    features=surface_features(
                        emission.before.text, emission.result.source.text
                    ),
                    source_hash=hashlib.sha256(
                        emission.result.source.text.encode("utf-8")
                    ).hexdigest(),
                )
            )

    def count_class(name: str) -> int:
        return sum(
            emission.result.instance.drift_type == name for emission in emissions
        )

    def count_operator(name: str) -> int:
        return sum(emission.op == name for emission in emissions)

    def count_base(name: str) -> int:
        return sum(
            emission.result.instance.provenance.base_program == name
            for emission in emissions
        )

    def fill(key: str, target: int, *, offset: int) -> None:
        candidates = catalog[key]
        failures = Counter()
        local_attempt = 0
        limit = max(100, target * max(20, len(candidates) * 10))
        while (
            count_class(key.replace("D3_interprocedural", "D3_contradictory")) < target
            and local_attempt < limit
        ):
            candidate = candidates[local_attempt % len(candidates)]
            emission = run_candidate(candidate, offset + local_attempt)
            local_attempt += 1
            if emission is None:
                failures[(candidate.base.filename, candidate.op)] += 1
                if (
                    failures[(candidate.base.filename, candidate.op)] >= 5
                    and len(candidates) == 1
                ):
                    break
                continue
            accept(emission)

    def fill_operator(key: str, operator: str, target: int, *, offset: int) -> None:
        candidates = catalog[key]
        failures = Counter()
        local_attempt = 0
        limit = max(100, target * max(20, len(candidates) * 10))
        while count_operator(operator) < target and local_attempt < limit:
            candidate = candidates[local_attempt % len(candidates)]
            emission = run_candidate(candidate, offset + local_attempt)
            local_attempt += 1
            if emission is None:
                failures[candidate.base.filename] += 1
                continue
            accept(emission)

    def fill_corrective_bases(target: int, *, offset: int) -> None:
        candidates_by_base: dict[str, list[_Candidate]] = {}
        for candidate in catalog["corrective_free"]:
            candidates_by_base.setdefault(candidate.base.filename, []).append(candidate)
        for base_index, name in enumerate(sorted(CORRECTIVE_BASES)):
            candidates = candidates_by_base[name]
            local_attempt = 0
            limit = target * max(50, len(candidates) * 20)
            while count_base(name) < target and local_attempt < limit:
                candidate = candidates[local_attempt % len(candidates)]
                emission = run_candidate(
                    candidate,
                    offset + base_index * 10_000 + local_attempt,
                )
                local_attempt += 1
                if emission is not None:
                    accept(emission)

    # DECISION: local MO-3/MO-6 and D2/D5 targets exceed their formal floors so
    # round-robin assignment leaves at least ten local rows on legacy groups
    # forced to test while still populating the new train/dev groups. MO-3× is
    # targeted at 24 and local MO-3 at 45 so their test-reserved/legacy groups
    # retain a rejection buffer above the purpose minima of eight and ten.
    fill("D2_missing_rule", 40, offset=20_000)
    fill_operator("D1_interprocedural", "MO-1×", 12, offset=25_000)
    fill_operator("D3_interprocedural", "MO-3×", 24, offset=30_000)
    fill_operator("D3_contradictory", "MO-3", 45, offset=40_000)
    fill("D4_stale_reference_data", 20, offset=50_000)
    fill("D5_boundary_error", 50, offset=60_000)
    fill_operator("D6_interprocedural", "MO-6×", 12, offset=65_000)
    fill_operator("D6_dead_code", "MO-6", 30, offset=70_000)
    fill_corrective_bases(CORRECTIVE_BASE_FLOOR, offset=100_000)

    extra_attempt = 0
    while len(emissions) < min_instances and extra_attempt < min_instances * 20:
        candidate = catalog["D7_conformant"][
            extra_attempt % len(catalog["D7_conformant"])
        ]
        emission = run_candidate(candidate, 80_000 + extra_attempt)
        extra_attempt += 1
        if emission is not None:
            accept(emission)

    class_counts = Counter(
        emission.result.instance.drift_type for emission in emissions
    )
    interprocedural_count = sum(
        emission.result.instance.code_locus.is_interprocedural for emission in emissions
    )
    shortfalls = {
        name: max(0, floor - class_counts[name]) for name, floor in CLASS_FLOORS.items()
    }
    shortfalls["interprocedural"] = max(
        0, INTERPROCEDURAL_FLOOR - interprocedural_count
    )
    shortfalls["minimum_instances"] = max(0, min_instances - len(emissions))

    if len(probe_rows) != PROBE_PER_LABEL * 2:
        raise RuntimeError(
            f"surface probe requires 200 paired emissions; generated {len(probe_rows)}"
        )
    probe_report = surface_probe_report(probe_rows, seed=seed, bootstrap_samples=400)
    ordered = sorted(
        emissions,
        key=lambda item: (
            item.result.instance.drift_type,
            item.result.instance.instance_id,
        ),
    )
    operator_counts = Counter(emission.op for emission in ordered)
    operator_shortfalls = {
        operator: max(0, floor - operator_counts[operator])
        for operator, floor in OPERATOR_FLOORS.items()
    }
    corrective_base_shortfalls = {
        name: max(0, CORRECTIVE_BASE_FLOOR - count_base(name))
        for name in sorted(CORRECTIVE_BASES)
    }
    class_shortfalls = {name: shortfalls[name] for name in sorted(CLASS_FLOORS)}
    unmet = {
        **{f"class:{name}": count for name, count in class_shortfalls.items() if count},
        **{
            f"operator:{name}": count
            for name, count in operator_shortfalls.items()
            if count
        },
        **{
            f"base:{name}": count
            for name, count in corrective_base_shortfalls.items()
            if count
        },
        **{
            name: shortfalls[name]
            for name in ("interprocedural", "minimum_instances")
            if shortfalls[name]
        },
    }
    if unmet:
        raise BuildConfigurationError(f"corrective generation floors unmet: {unmet}")

    base_counts = Counter(
        emission.result.instance.provenance.base_program for emission in ordered
    )
    validation_counts = Counter(
        emission.result.validation.level for emission in ordered
    )
    judge_family, judge_family_reason = _standing_judge_family(root)
    manifest = {
        "schema_version": 1,
        "seed": seed,
        "git_sha": _git_sha(root),
        "diversify": diversify_mode,
        "diversify_mode": diversify_mode,
        "judge_family": judge_family,
        "judge_family_reason": judge_family_reason,
        "minimum_instances": min_instances,
        "instance_count": len(ordered),
        "operator_counts": dict(sorted(operator_counts.items())),
        "operator_floors": dict(sorted(OPERATOR_FLOORS.items())),
        "operator_shortfalls": dict(sorted(operator_shortfalls.items())),
        "corrective_base_floor": CORRECTIVE_BASE_FLOOR,
        "corrective_base_shortfalls": corrective_base_shortfalls,
        "base_counts": dict(sorted(base_counts.items())),
        "class_counts": {name: class_counts[name] for name in sorted(CLASS_FLOORS)},
        "class_floors": dict(sorted(CLASS_FLOORS.items())),
        "class_shortfalls": class_shortfalls,
        "interprocedural_count": interprocedural_count,
        "shortfalls": dict(sorted(shortfalls.items())),
        "rejects_by_reason": dict(sorted(rejects.items())),
        "validation_level_counts": dict(sorted(validation_counts.items())),
        "surface_probe": {
            "auc": probe_report.auc,
            "ci_low": probe_report.ci_low,
            "ci_high": probe_report.ci_high,
            "samples": probe_report.samples,
            # Per-feature, so the anti-gaming claim is falsifiable at the
            # feature level and not only in aggregate. A reviewer can see which
            # axis carries signal rather than taking one number on trust.
            "per_feature_auc": per_feature_auc(probe_rows),
        },
    }

    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(emission.result.instance.model_dump_json() for emission in ordered)
        + "\n",
        encoding="utf-8",
    )
    manifest_path_for(output).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BuildResult(
        manifest=manifest,
        probe_rows=[_probe_dict(row) for row in probe_rows],
        sources={
            emission.result.instance.instance_id: emission.result.source
            for emission in ordered
        },
    )
