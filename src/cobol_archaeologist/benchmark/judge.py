"""Plausibility judging of generated benchmark rows.

The judge is Claude, a different model family from the detector under test
(``SYSTEM_FAMILY``). The flow is:

1. ``write_packets`` renders one review document per row: the clause and every
   mutated locus with surrounding source. No label, class, or gold rationale is
   shown.
2. The judge writes one ``Judgement`` per row to a JSONL file, applying
   ``docs/judge-rubric.md``.
3. ``apply_verdicts`` keeps the plausible rows and writes the rest to a
   rejected file. Judgements from the detector's model family are refused.

``data/benchmark/judgements.jsonl`` records the verdicts behind the existing
train/dev rows. Those were made by OpenAI models when the system under test
was Claude; they remain the historical record and are not re-applied.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cobol_archaeologist.eval.materialize import MaterializedSource, materialize
from cobol_archaeologist.schemas import DriftInstance, DriftType

Verdict = Literal["plausible", "implausible", "unsure"]
SYSTEM_FAMILY = "openai"  # the detector under test runs gpt-6-luna
PLAUSIBLE_RATE_GATE = 0.90


class FamilyIntegrityError(ValueError):
    """Raised when the judge shares a model family with the detector."""


class PlausibilityGateError(RuntimeError):
    """Raised when fewer than 90% of judged rows are plausible."""


class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    drift_type: DriftType
    is_interprocedural: bool
    verdict: Verdict
    reason: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_family: str = Field(min_length=1)

    @field_validator("model_family")
    @classmethod
    def _canonical(cls, family: str) -> str:
        return canonical_family(family)


def canonical_family(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {"claude": "anthropic", "gpt": "openai", "gemini": "google"}
    return aliases.get(normalized, normalized)


def infer_model_family(model: str) -> str | None:
    normalized = model.lower()
    if "claude" in normalized or "anthropic" in normalized:
        return "anthropic"
    if "gemini" in normalized or "google" in normalized:
        return "google"
    if "gpt" in normalized or "openai" in normalized or "luna" in normalized:
        return "openai"
    return None


def load_instances(path: str | Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_judgements(path: str | Path) -> list[Judgement]:
    judgements = [
        Judgement.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for judgement in judgements:
        inferred = infer_model_family(judgement.model)
        if inferred is not None and inferred != judgement.model_family:
            raise FamilyIntegrityError(
                f"model {judgement.model!r} belongs to {inferred}, "
                f"not {judgement.model_family}"
            )
    return judgements


def _locus_text(source: MaterializedSource, file: str | None) -> str:
    return source.files[file or source.main_file]


def render_packet(instance: DriftInstance, source: MaterializedSource) -> str:
    """Clause plus every mutated locus with context; no label or rationale."""

    clause = instance.regulation_clause
    sections = [
        f"# {instance.instance_id}",
        "",
        "## Regulation clause",
        f"{clause.doc} {clause.clause_id} ({clause.version})",
        clause.text,
    ]
    for index, locus in enumerate(instance.code_locus.loci, 1):
        lines = _locus_text(source, locus.file).splitlines()
        start = max(1, locus.line_span[0] - 10)
        end = min(len(lines), locus.line_span[1] + 10)
        numbered = "\n".join(
            f"{number:>6}: {lines[number - 1]}" for number in range(start, end + 1)
        )
        sections += [
            "",
            f"## Mutated locus {index}",
            (
                f"program={locus.program}; file={locus.file or source.main_file}; "
                f"paragraph={locus.paragraph or '<none>'}; "
                f"span={locus.line_span[0]}-{locus.line_span[1]}"
            ),
            "```cobol",
            numbered,
            "```",
        ]
    sections += [
        "",
        "## Question",
        (
            "Does this look like drift that could occur in real legacy code, or "
            "like an artificial edit? Verdict: plausible, implausible, or unsure."
        ),
    ]
    return "\n".join(sections) + "\n"


def write_packets(
    instances_path: str | Path,
    out_path: str | Path,
    *,
    programs_root: Path | None = None,
) -> int:
    """Write every row's review packet into one Markdown file."""

    rows = load_instances(instances_path)
    kwargs = {} if programs_root is None else {"programs_root": programs_root}
    packets = [render_packet(row, materialize(row, **kwargs)) for row in rows]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n---\n\n".join(packets), encoding="utf-8", newline="\n")
    return len(packets)


def plausible_rate(judgements: list[Judgement]) -> float:
    if not judgements:
        raise PlausibilityGateError("no judgements")
    return sum(item.verdict == "plausible" for item in judgements) / len(judgements)


def plausibility_gate(judgements: list[Judgement]) -> float:
    rate = plausible_rate(judgements)
    if rate < PLAUSIBLE_RATE_GATE:
        raise PlausibilityGateError(
            f"plausibility rate {rate:.1%} is below the required 90%"
        )
    return rate


def apply_verdicts(
    instances_path: str | Path,
    judgements: list[Judgement],
    accepted_path: str | Path,
    rejected_path: str | Path,
) -> dict[str, int | float]:
    """Keep plausible rows; write every other row with its judgement."""

    for judgement in judgements:
        if judgement.model_family == SYSTEM_FAMILY:
            raise FamilyIntegrityError(
                f"{judgement.instance_id} was judged by {judgement.model}, the "
                "detector's model family; rejudge it with an independent judge"
            )
    instances = load_instances(instances_path)
    by_id = {item.instance_id: item for item in judgements}
    if len(by_id) != len(judgements):
        raise ValueError("judgements contain duplicate instance ids")
    if set(by_id) != {item.instance_id for item in instances}:
        raise ValueError("every row needs exactly one judgement")
    for instance in instances:
        judgement = by_id[instance.instance_id]
        if (
            judgement.drift_type != instance.drift_type
            or judgement.is_interprocedural != instance.code_locus.is_interprocedural
        ):
            raise ValueError(f"judgement metadata differs for {instance.instance_id}")
    accepted = [
        row for row in instances if by_id[row.instance_id].verdict == "plausible"
    ]
    rejected = [
        {
            "instance": row.model_dump(mode="json"),
            "judgement": by_id[row.instance_id].model_dump(mode="json"),
        }
        for row in instances
        if by_id[row.instance_id].verdict != "plausible"
    ]
    Path(accepted_path).write_text(
        "".join(row.model_dump_json() + "\n" for row in accepted),
        encoding="utf-8",
        newline="\n",
    )
    Path(rejected_path).write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rejected
        ),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "judged": len(judgements),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "plausible_rate": plausible_rate(judgements),
    }
