"""T2.4 external-family plausibility judging harness."""

from __future__ import annotations

import json
import random
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.benchmark.build import build_benchmark, manifest_path_for
from cobol_archaeologist.benchmark.mutate import ProgramSource
from cobol_archaeologist.schemas import DriftInstance, DriftType


Verdict = Literal["plausible", "implausible", "unsure"]
Transport = Callable[["JudgeConfig", str], str]
SYSTEM_FAMILY = "anthropic"


class FamilyIntegrityError(RuntimeError):
    """Raised when judge and system-under-test families are not independent."""


class JudgeConfigurationError(RuntimeError):
    """Raised when endpoint configuration or source reconstruction is invalid."""


class PlausibilityGateError(RuntimeError):
    """Raised when fewer than 90% of reviewed instances are plausible."""


class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    drift_type: DriftType
    is_interprocedural: bool
    verdict: Verdict
    reason: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_family: str = Field(min_length=1)


class UnsureAdjudication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    verdict: Literal["plausible", "implausible"]
    reason: str = Field(min_length=1)


class _VerdictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    reason: str = Field(min_length=1)


@dataclass(frozen=True)
class JudgeConfig:
    endpoint: str
    api_key: str
    model: str
    model_family: str
    reasoning_effort: str | None = None
    timeout_seconds: float = 60.0

    def validate(self) -> None:
        if not self.endpoint or not self.api_key or not self.model:
            raise JudgeConfigurationError(
                "judge endpoint, API key, and model must all be configured"
            )
        judge = canonical_family(self.model_family)
        system = SYSTEM_FAMILY
        inferred = infer_model_family(self.model)
        if inferred is not None and inferred != judge:
            raise FamilyIntegrityError(
                f"model {self.model!r} belongs to {inferred}, not configured family {judge}"
            )
        if judge == system:
            raise FamilyIntegrityError(
                f"judge family {judge!r} matches system-under-test family {system!r}"
            )
        if self.reasoning_effort not in {
            None,
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise JudgeConfigurationError(
                f"unsupported reasoning effort {self.reasoning_effort!r}"
            )


def canonical_family(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "claude": "anthropic",
        "anthropic": "anthropic",
        "gpt": "openai",
        "openai": "openai",
        "gemini": "google",
        "google": "google",
    }
    return aliases.get(normalized, normalized)


def infer_model_family(model: str) -> str | None:
    normalized = model.lower()
    if "claude" in normalized or "anthropic" in normalized:
        return "anthropic"
    if "gemini" in normalized or "google" in normalized:
        return "google"
    if "gpt" in normalized or "openai" in normalized:
        return "openai"
    return None


def load_judgements(path: str | Path) -> list[Judgement]:
    return [
        Judgement.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_unsure_adjudications(path: str | Path) -> list[UnsureAdjudication]:
    return [
        UnsureAdjudication.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_instances(path: str | Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def reconstruct_sources(
    instances_path: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> dict[str, ProgramSource]:
    """Deterministically rebuild T2.3 sources without changing frozen schema v2."""

    # DECISION: reconstruct exact deterministic T2.3 outputs from the run
    # manifest instead of adding source text/path fields to frozen schema v2.
    instances_path = Path(instances_path)
    manifest = json.loads(manifest_path_for(instances_path).read_text(encoding="utf-8"))
    if manifest.get("diversify") != "deterministic":
        raise JudgeConfigurationError(
            "source reconstruction requires a deterministic T2.3 manifest"
        )
    with tempfile.TemporaryDirectory(prefix="t24_sources_") as tmp:
        rebuilt = build_benchmark(
            seed=int(manifest["seed"]),
            out_path=Path(tmp) / "drift_instances.jsonl",
            min_instances=int(manifest["minimum_instances"]),
            diversify_mode="deterministic",
            repository_root=repository_root,
        )
    expected = {item.instance_id for item in _load_instances(instances_path)}
    if set(rebuilt.sources) != expected:
        missing = sorted(expected - set(rebuilt.sources))
        extra = sorted(set(rebuilt.sources) - expected)
        raise JudgeConfigurationError(
            f"rebuilt source identity mismatch; missing={missing[:3]}, extra={extra[:3]}"
        )
    return rebuilt.sources


def _locus_source(source: ProgramSource, file: str | None) -> str:
    if file is None or file == source.filename:
        return source.text
    try:
        return source.files[file]
    except KeyError as exc:
        raise JudgeConfigurationError(
            f"mutated source {source.filename} lacks locus file {file!r}"
        ) from exc


def render_prompt(instance: DriftInstance, source: ProgramSource) -> str:
    """Render clause and mutated loci without leaking labels or gold rationale."""

    sections = [
        "# Legacy COBOL plausibility review",
        "",
        "## Regulation clause",
        (
            f"{instance.regulation_clause.doc} "
            f"{instance.regulation_clause.clause_id} "
            f"({instance.regulation_clause.version})"
        ),
        instance.regulation_clause.text,
    ]
    for index, locus in enumerate(instance.code_locus.loci, 1):
        lines = _locus_source(source, locus.file).splitlines()
        start = max(1, locus.line_span[0] - 10)
        end = min(len(lines), locus.line_span[1] + 10)
        numbered = "\n".join(
            f"{line_number:>6}: {lines[line_number - 1]}"
            for line_number in range(start, end + 1)
        )
        sections.extend(
            [
                "",
                f"## Mutated locus {index}",
                (
                    f"program={locus.program}; file={locus.file or source.filename}; "
                    f"paragraph={locus.paragraph or '<none>'}; "
                    f"mutated_span={locus.line_span[0]}-{locus.line_span[1]}"
                ),
                "```cobol",
                numbered,
                "```",
            ]
        )
    sections.extend(
        [
            "",
            "## Question",
            (
                "Does this look like drift that could occur in real legacy code, "
                "or like an artificial edit? Return JSON only: "
                '{"verdict":"plausible|implausible|unsure","reason":"..."}'
            ),
        ]
    )
    return "\n".join(sections)


def stratified_sample(
    instances: list[DriftInstance], *, count: int, seed: int
) -> list[DriftInstance]:
    groups: dict[str, list[DriftInstance]] = defaultdict(list)
    for instance in instances:
        groups[instance.drift_type].append(instance)
    if count < len(groups):
        raise ValueError(f"sample {count} cannot cover {len(groups)} drift classes")
    if count > len(instances):
        raise ValueError("sample cannot exceed the input size")

    rng = random.Random(seed)
    for items in groups.values():
        items.sort(key=lambda item: item.instance_id)
        rng.shuffle(items)
    selected = [groups[name].pop() for name in sorted(groups)]
    if not any(item.code_locus.is_interprocedural for item in selected):
        cross = next(
            (
                item
                for name in sorted(groups)
                for item in groups[name]
                if item.code_locus.is_interprocedural
            ),
            None,
        )
        if cross is None:
            raise ValueError("input has no interprocedural stratum")
        groups[cross.drift_type].remove(cross)
        selected.append(cross)
    if not any(not item.code_locus.is_interprocedural for item in selected):
        raise ValueError("input has no local stratum")

    names = sorted(groups)
    cursor = 0
    while len(selected) < count:
        name = names[cursor % len(names)]
        cursor += 1
        if groups[name]:
            selected.append(groups[name].pop())
        if cursor > len(instances) * len(names):  # pragma: no cover - safety bound
            raise RuntimeError("stratified sampler exhausted unexpectedly")
    return selected


def _endpoint_url(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    return (
        normalized
        if normalized.endswith("/chat/completions")
        else f"{normalized}/chat/completions"
    )


def _endpoint_transport(config: JudgeConfig, prompt: str) -> str:
    request_payload: dict[str, object] = {
        "model": config.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an independent legacy-COBOL plausibility judge. "
                    "Apply the supplied regulation and code only; output JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    # DECISION: reasoning models reject non-default temperature values. Keep
    # effort optional so non-OpenAI compatible endpoints do not receive an
    # OpenAI-specific field, and omit temperature for provider portability.
    if config.reasoning_effort is not None:
        request_payload["reasoning_effort"] = config.reasoning_effort
    payload = json.dumps(request_payload).encode("utf-8")
    request = urllib.request.Request(
        _endpoint_url(config.endpoint),
        data=payload,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                request, timeout=config.timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
            return str(body["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            # API error bodies contain request diagnostics, not the submitted
            # Authorization header. Cap the text to keep CLI output bounded.
            detail = body[:2000] if body else str(exc)
            last_error = RuntimeError(f"HTTP {exc.code}: {detail}")
            if attempt < 2:
                time.sleep(2**attempt)
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise JudgeConfigurationError(
        f"judge endpoint failed after 3 attempts: {last_error}"
    )


def _parse_verdict(
    content: str, instance: DriftInstance, config: JudgeConfig
) -> Judgement:
    try:
        payload = _VerdictPayload.model_validate_json(content)
    except Exception as exc:
        raise JudgeConfigurationError(
            f"judge returned invalid verdict for {instance.instance_id}: {exc}"
        ) from exc
    return Judgement(
        instance_id=instance.instance_id,
        drift_type=instance.drift_type,
        is_interprocedural=instance.code_locus.is_interprocedural,
        verdict=payload.verdict,
        reason=payload.reason,
        model=config.model,
        model_family=canonical_family(config.model_family),
    )


def plausibility_gate(judgements: list[Judgement]) -> float:
    if not judgements:
        raise PlausibilityGateError("plausibility gate has no judgements")
    rate = sum(item.verdict == "plausible" for item in judgements) / len(judgements)
    if rate < 0.9:
        raise PlausibilityGateError(
            f"plausibility rate {rate:.1%} is below the required 90%"
        )
    return rate


def _write_jsonl(models: list[BaseModel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(item.model_dump_json() for item in models) + "\n",
        encoding="utf-8",
    )


def _write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_checkpoint(
    path: Path,
    selected: list[DriftInstance],
    config: JudgeConfig,
) -> list[Judgement]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        judgements = load_judgements(path)
    except (OSError, ValueError) as exc:
        raise JudgeConfigurationError(
            f"cannot resume invalid judgement checkpoint {path}: {exc}"
        ) from exc
    if len(judgements) > len(selected):
        raise JudgeConfigurationError(
            f"judgement checkpoint {path} has more rows than the selected input"
        )
    family = canonical_family(config.model_family)
    for index, judgement in enumerate(judgements):
        instance = selected[index]
        matches = (
            judgement.instance_id == instance.instance_id
            and judgement.drift_type == instance.drift_type
            and judgement.is_interprocedural
            == instance.code_locus.is_interprocedural
            and judgement.model == config.model
            and judgement.model_family == family
        )
        if not matches:
            raise JudgeConfigurationError(
                f"judgement checkpoint {path} does not match the current "
                f"input/configuration at row {index + 1}; use a different --out "
                "or remove the stale checkpoint"
            )
    return judgements


def _load_reuse_cache(
    path: str | Path | None,
    selected: list[DriftInstance],
    config: JudgeConfig,
) -> dict[str, Judgement]:
    if path is None:
        return {}
    path = Path(path)
    try:
        judgements = load_judgements(path)
    except (OSError, ValueError) as exc:
        raise JudgeConfigurationError(
            f"cannot load judgement reuse file {path}: {exc}"
        ) from exc
    by_id = {judgement.instance_id: judgement for judgement in judgements}
    if len(by_id) != len(judgements):
        raise JudgeConfigurationError(
            f"judgement reuse file {path} contains duplicate instance IDs"
        )
    family = canonical_family(config.model_family)
    reusable: dict[str, Judgement] = {}
    for instance in selected:
        judgement = by_id.get(instance.instance_id)
        if judgement is None:
            continue
        matches = (
            judgement.drift_type == instance.drift_type
            and judgement.is_interprocedural
            == instance.code_locus.is_interprocedural
            and judgement.model == config.model
            and judgement.model_family == family
        )
        if not matches:
            raise JudgeConfigurationError(
                f"judgement reuse file {path} has incompatible metadata for "
                f"{instance.instance_id}"
            )
        reusable[instance.instance_id] = judgement
    return reusable


def judge_benchmark(
    *,
    instances_path: str | Path,
    output_path: str | Path,
    config: JudgeConfig,
    sample: int | None = None,
    seed: int = 2400,
    reuse_path: str | Path | None = None,
    transport: Transport | None = None,
    source_index: dict[str, ProgramSource] | None = None,
) -> dict:
    config.validate()
    instances_path = Path(instances_path)
    instances = _load_instances(instances_path)
    selected = (
        stratified_sample(instances, count=sample, seed=seed)
        if sample is not None
        else instances
    )
    call = transport or _endpoint_transport
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    judgements = _load_checkpoint(output_path, selected, config)
    resumed_count = len(judgements)
    reuse_cache = _load_reuse_cache(reuse_path, selected, config)
    reused_count = 0
    needs_endpoint = any(
        instance.instance_id not in reuse_cache
        for instance in selected[resumed_count:]
    )
    sources = (
        source_index or reconstruct_sources(instances_path)
        if needs_endpoint
        else {}
    )
    if resumed_count == 0:
        output_path.write_text("", encoding="utf-8")
    with output_path.open("a", encoding="utf-8", newline="\n") as checkpoint:
        for instance in selected[resumed_count:]:
            judgement = reuse_cache.get(instance.instance_id)
            if judgement is not None:
                reused_count += 1
            else:
                try:
                    content = call(
                        config,
                        render_prompt(instance, sources[instance.instance_id]),
                    )
                    judgement = _parse_verdict(content, instance, config)
                except JudgeConfigurationError as exc:
                    raise JudgeConfigurationError(
                        f"{exc}; {len(judgements)}/{len(selected)} judgements "
                        f"checkpointed at {output_path}"
                    ) from exc
            judgements.append(judgement)
            checkpoint.write(judgement.model_dump_json() + "\n")
            checkpoint.flush()

    plausible_rate = sum(item.verdict == "plausible" for item in judgements) / len(
        judgements
    )
    try:
        plausibility_gate(judgements)
        gate_passed = True
    except PlausibilityGateError:
        gate_passed = False
    counts = Counter(item.verdict for item in judgements)
    report = {
        "sample_size": len(judgements),
        "resumed_count": resumed_count,
        "reused_count": reused_count,
        "full_set": sample is None,
        "seed": seed,
        "model": config.model,
        "model_family": canonical_family(config.model_family),
        "reasoning_effort": config.reasoning_effort,
        "system_family": SYSTEM_FAMILY,
        "verdict_counts": {
            name: counts[name] for name in ("plausible", "implausible", "unsure")
        },
        "plausible_rate": plausible_rate,
        "gate_passed": gate_passed,
    }
    manifest_path = manifest_path_for(instances_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    judging = manifest.get("judging", {})
    judging.update(
        {
            "model": config.model,
            "model_family": canonical_family(config.model_family),
            "reasoning_effort": config.reasoning_effort,
            "system_family": SYSTEM_FAMILY,
        }
    )
    judging["sample" if sample is not None else "full"] = report
    manifest["judging"] = judging
    _write_manifest(manifest_path, manifest)
    return report


def apply_drop_policy(
    instances_path: str | Path,
    judgements: list[Judgement],
    accepted_path: str | Path,
    rejected_dir: str | Path,
    adjudications: list[UnsureAdjudication] | None = None,
) -> dict[str, int]:
    instances = _load_instances(instances_path)
    by_id = {item.instance_id: item for item in judgements}
    if set(by_id) != {item.instance_id for item in instances}:
        raise ValueError("drop policy requires one judgement for every input instance")
    adjudication_by_id = {
        item.instance_id: item for item in adjudications or []
    }
    if adjudications is not None:
        if len(adjudication_by_id) != len(adjudications):
            raise ValueError("unsure adjudications contain duplicate instance IDs")
        unsure_ids = {
            item.instance_id for item in judgements if item.verdict == "unsure"
        }
        if set(adjudication_by_id) != unsure_ids:
            raise ValueError(
                "unsure adjudications must cover every and only unsure judgement"
            )

    accepted: list[DriftInstance] = []
    rejected: dict[str, list[dict]] = {"implausible": [], "unsure": []}
    for instance in instances:
        judgement = by_id[instance.instance_id]
        adjudication = adjudication_by_id.get(instance.instance_id)
        effective_verdict = (
            adjudication.verdict if adjudication is not None else judgement.verdict
        )
        if effective_verdict == "plausible":
            accepted.append(instance)
        else:
            row = {
                "instance": instance.model_dump(mode="json"),
                "judgement": judgement.model_dump(mode="json"),
            }
            if adjudication is not None:
                row["adjudication"] = adjudication.model_dump(mode="json")
            rejected[effective_verdict].append(row)
    _write_jsonl(accepted, Path(accepted_path))
    rejected_dir = Path(rejected_dir)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    for verdict in ("implausible", "unsure"):
        path = rejected_dir / f"{verdict}.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                for row in rejected[verdict]
            )
            + ("\n" if rejected[verdict] else ""),
            encoding="utf-8",
        )
    return {
        "accepted": len(accepted),
        "implausible": len(rejected["implausible"]),
        "unsure": len(rejected["unsure"]),
        "adjudicated": len(adjudication_by_id),
    }


def record_human_agreement(
    judgements_path: str | Path,
    reviews_path: str | Path,
    manifest_path: str | Path,
) -> dict[str, int | float]:
    judgements = {item.instance_id: item for item in load_judgements(judgements_path)}
    reviews = [
        json.loads(line)
        for line in Path(reviews_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(reviews) != 15 or len({row.get("instance_id") for row in reviews}) != 15:
        raise ValueError("human spot-check requires exactly 15 unique reviews")
    agreed = 0
    for row in reviews:
        instance_id = str(row.get("instance_id", ""))
        verdict = row.get("verdict")
        if instance_id not in judgements:
            raise ValueError(
                f"human review references unknown instance {instance_id!r}"
            )
        if verdict not in {"plausible", "implausible", "unsure"}:
            raise ValueError(f"invalid human verdict {verdict!r}")
        agreed += verdict == judgements[instance_id].verdict
    report: dict[str, int | float] = {
        "reviewed": 15,
        "agreed": agreed,
        "rate": agreed / 15,
    }
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("judging", {})["human_agreement"] = report
    _write_manifest(manifest_path, manifest)
    return report
