"""T2.3 deterministic synthetic benchmark build orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import random
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
    mutate,
)
from cobol_archaeologist.benchmark.surface import (
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

    cbtrn02 = _carddemo_base(
        root,
        "CBTRN02C.cbl",
        touched_variables=(
            "WS-VALIDATION-FAIL-REASON",
            "ACCT-CREDIT-LIMIT",
            "WS-TEMP-BAL",
        ),
    )
    cbact04 = _carddemo_base(
        root,
        "CBACT04C.cbl",
        touched_variables=("WS-MONTHLY-INT", "TRAN-CAT-BAL", "WS-TOTAL-INT"),
    )

    # DECISION: the sole D4 scale base normalizes the seed's shipped day-basis
    # declaration into its shipped shared copybook. It remains seed-derived and
    # compiled, while making the mutated 88-level list an actually consumed file.
    d4_base = _seed_base(
        programs,
        "CLOSPEN3.cbl",
        touched_variables=("WS-WORK-DAYS-ELAPSED", "WS-DAY-BASIS"),
    )
    d4_base = replace(
        d4_base,
        text=d4_base.text.replace(
            "       WORKING-STORAGE SECTION.",
            "       WORKING-STORAGE SECTION.\n       COPY WSDAYBAS.",
        ),
        files={"WSDAYBAS.cpy": (programs / "WSDAYBAS.cpy").read_text(encoding="utf-8")},
    )

    d1 = [_Candidate(base, record, "MO-1") for base, record in hosted]
    d5 = [_Candidate(base, record, "MO-5") for base, record in hosted]
    d7 = [_Candidate(base, record, "MO-0") for base, record in hosted]
    return {
        "D1_stale_threshold": d1,
        "D2_missing_rule": [_Candidate(hosted[1][0], hosted[1][1], "MO-2")],
        "D3_contradictory": [_Candidate(late_fee, clauses["CC-09b-v"], "MO-3")],
        "D3_interprocedural": [_Candidate(cbtrn02, clauses["CC-06b-v"], "MO-3×")],
        "D4_stale_reference_data": [_Candidate(d4_base, clauses["CC-29"], "MO-4")],
        "D5_boundary_error": d5,
        "D6_dead_code": [_Candidate(cbact04, clauses["CC-09b-ii"], "MO-6")],
        "D7_conformant": d7,
    }


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
    emissions: list[_Emission] = []
    seen_ids: set[str] = set()
    rejects: Counter[str] = Counter(
        {
            "MO-1×: no conformant copybook-cutoff base in the 12 seeds or CardDemo": 1,
            "MO-6×: no conformant cross-program compliance-flag base in the 12 seeds or CardDemo": 1,
        }
    )

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

    fill("D2_missing_rule", 20, offset=20_000)
    fill("D3_interprocedural", 30, offset=30_000)
    if not any(emission.op == "MO-3" for emission in emissions):
        candidate = catalog["D3_contradictory"][0]
        emission = run_candidate(candidate, 39_999)
        if emission is not None:
            accept(emission)
    fill("D3_contradictory", 20, offset=40_000)
    fill("D4_stale_reference_data", 20, offset=50_000)
    fill("D5_boundary_error", 20, offset=60_000)
    fill("D6_dead_code", 20, offset=70_000)

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
    base_counts = Counter(
        emission.result.instance.provenance.base_program for emission in ordered
    )
    validation_counts = Counter(
        emission.result.validation.level for emission in ordered
    )
    manifest = {
        "schema_version": 1,
        "seed": seed,
        "git_sha": _git_sha(root),
        "diversify": diversify_mode,
        "minimum_instances": min_instances,
        "instance_count": len(ordered),
        "operator_counts": dict(sorted(operator_counts.items())),
        "base_counts": dict(sorted(base_counts.items())),
        "class_counts": {name: class_counts[name] for name in sorted(CLASS_FLOORS)},
        "class_floors": dict(sorted(CLASS_FLOORS.items())),
        "interprocedural_count": interprocedural_count,
        "shortfalls": dict(sorted(shortfalls.items())),
        "rejects_by_reason": dict(sorted(rejects.items())),
        "validation_level_counts": dict(sorted(validation_counts.items())),
        "surface_probe": {
            "auc": probe_report.auc,
            "ci_low": probe_report.ci_low,
            "ci_high": probe_report.ci_high,
            "samples": probe_report.samples,
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
