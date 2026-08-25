"""Freeze one fresh candidate derived from the sealed reserve-v1 gap."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from cobol_archaeologist.benchmark.t6_replacement import (
    ReplacementPlanItem,
    ReplacementSideInput,
    build_replacement_prompt,
    source_sha256,
    validate_replacement_batch_ledger,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin
from cobol_archaeologist.schemas import CodeLocus, SourceLocus


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("reserve-v2 artifact escapes repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=source_sha256(resolved)
    )


def _write_once(path: Path, value: bytes) -> None:
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"refusing to overwrite reserve-v2 artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _opaque(prefix: str, seed: str, length: int) -> str:
    return prefix + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def _prior_model_ids(
    *, root: Path, ledger_path: Path, seen: set[Path] | None = None
) -> tuple[set[str], set[str], set[str]]:
    seen = set() if seen is None else seen
    resolved = ledger_path.resolve()
    if resolved in seen:
        raise ValueError("replacement ledger lineage contains a cycle")
    seen.add(resolved)
    _, plans, _ = validate_replacement_batch_ledger(
        root=root, ledger_path=resolved
    )
    calls = {plan.replacement_call_id for plan in plans}
    reviews = {side.review_item_id for plan in plans for side in plan.sides}
    aliases = {side.source_alias for plan in plans for side in plan.sides}
    prior_ledgers = {
        plan.prior_batch_ledger.path: plan.prior_batch_ledger
        for plan in plans
        if plan.prior_batch_ledger is not None
    }
    for prior in prior_ledgers.values():
        prior_calls, prior_reviews, prior_aliases = _prior_model_ids(
            root=root, ledger_path=root / prior.path, seen=seen
        )
        calls.update(prior_calls)
        reviews.update(prior_reviews)
        aliases.update(prior_aliases)
    return calls, reviews, aliases


def prepare(
    *,
    root: Path,
    ledger_path: Path,
    output_dir: Path,
    generation: Literal["reserve-v2", "reserve-v3"] = "reserve-v2",
) -> Path:
    root = root.resolve()
    ledger, plans, accepted = validate_replacement_batch_ledger(
        root=root, ledger_path=ledger_path
    )
    accepted_ids = {plan.replacement_id for plan, _ in accepted}
    missing = [plan for plan in plans if plan.replacement_id not in accepted_ids]
    if len(missing) != 1 or missing[0].rejected_pair_id != "t6v2-candidate-05":
        raise ValueError("fresh reserve requires the exact sealed candidate-05 gap")
    rejected = missing[0]
    ledger_pin = _pin(root, ledger_path)
    is_v3 = generation == "reserve-v3"
    replacement_id = (
        "t6v2-replacement-10" if is_v3 else "t6v2-replacement-09"
    )
    superseded_pin = (
        _pin(
            root,
            root
            / "data/benchmark/t6-v2/replacements/review-reserve-v2/"
            "prompt-manifest.coordinator-private.json",
        )
        if is_v3
        else None
    )
    lineage = (
        f"{generation}:{ledger_pin.sha256}:{superseded_pin.sha256}:{replacement_id}"
        if superseded_pin is not None
        else f"{generation}:{ledger_pin.sha256}:{replacement_id}"
    )
    source_path = (
        root
        / "data/benchmark/t6-v2/replacements/programs/"
        f"T6V2{'R4E' if is_v3 else 'R4D'}.cbl"
    )
    source_text = source_path.read_text(encoding="utf-8")
    authorities = list(rejected.sides)
    authorities.reverse()
    plan = ReplacementPlanItem(
        schema_version="1",
        replacement_id=replacement_id,
        rejected_pair_id=rejected.rejected_pair_id,
        replacement_call_id=_opaque("rcall-", lineage, 12),
        prompt_protocol_version=(
            "v4_explicit_schema" if is_v3 else "v3_decision_semantics"
        ),
        prior_protocol_diagnostic=rejected.prior_protocol_diagnostic,
        prior_batch_ledger=ledger_pin,
        source=_pin(root, source_path),
        shared_source_text=source_text,
        code_locus=CodeLocus(
            loci=(
                SourceLocus(
                    program="BOF3G7" if is_v3 else "BOE9F5",
                    paragraph="1000-MAIN",
                    file=None,
                    line_span=(9, len(source_text.splitlines())),
                ),
            ),
            slice_vars=(),
            is_interprocedural=False,
        ),
        host_design_note=(
            "The source directly implements the older authority behavior while "
            "deliberately omitting only the later rule change."
        ),
        sides=tuple(
            ReplacementSideInput(
                position=position,
                review_item_id=_opaque(
                    "rvw-", f"{lineage}:{position}:review", 8
                ),
                source_alias=_opaque(
                    "src-", f"{lineage}:{position}:source", 12
                ),
                authority=side.authority,
            )
            for position, side in zip(("alpha", "beta"), authorities, strict=True)
        ),
    )
    prior_calls, prior_reviews, prior_aliases = _prior_model_ids(
        root=root, ledger_path=ledger_path
    )
    if (
        plan.replacement_call_id in prior_calls
        or prior_reviews.intersection(side.review_item_id for side in plan.sides)
        or prior_aliases.intersection(side.source_alias for side in plan.sides)
        or plan.source.sha256 in {prior.source.sha256 for prior in plans}
    ):
        raise ValueError("fresh reserve reuses prior source or model-visible identity")
    plan_path = output_dir / "replacement-plan.coordinator-private.jsonl"
    _write_once(plan_path, (plan.model_dump_json() + "\n").encode("utf-8"))
    prompt = build_replacement_prompt(plan).encode("utf-8")
    forbidden = (
        "proposal",
        "gold",
        "data/benchmark",
        "replacement",
        "candidate",
        "temporal",
        "target",
        "flip",
        "one d7 and one",
        "validated_flip",
        "rejected_",
    )
    if any(token in prompt.decode("utf-8").lower() for token in forbidden):
        raise ValueError("fresh reserve prompt leaks coordinator or expected outcome")
    prompt_path = output_dir / "prompts" / "reserve-01.txt"
    _write_once(prompt_path, prompt)
    manifest = {
        "schema_version": "1",
        "freeze_version": generation,
        "model_id": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "fork_turns": "none",
        "tools_authorized": 0,
        "prior_pair_context_included": False,
        "correction_audit": ledger.correction_audit.model_dump(mode="json"),
        "prior_batch_ledger": ledger_pin.model_dump(mode="json"),
        "replacement_plan": _pin(root, plan_path).model_dump(mode="json"),
        "replacement_order": [replacement_id],
        "replacement_to_rejected_original": {
            replacement_id: rejected.rejected_pair_id
        },
        "calls": [
            {
                "replacement_id": replacement_id,
                "replacement_call_id": plan.replacement_call_id,
                "review_item_order": [side.review_item_id for side in plan.sides],
                "prompt": _pin(root, prompt_path).model_dump(mode="json"),
                "prompt_utf8_length": len(prompt),
            }
        ],
    }
    if superseded_pin is not None:
        manifest["superseded_uncalled_freeze"] = superseded_pin.model_dump(
            mode="json"
        )
    manifest_path = output_dir / "prompt-manifest.coordinator-private.json"
    _write_once(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(
            "data/benchmark/t6-v2/replacements/evidence/"
            "review-reserve-v1-ledger/batch-ledger-manifest.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/benchmark/t6-v2/replacements/review-reserve-v3"),
    )
    parser.add_argument(
        "--generation", choices=("reserve-v2", "reserve-v3"), default="reserve-v3"
    )
    args = parser.parse_args()
    root = args.root.resolve()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    print(
        prepare(
            root=root,
            ledger_path=resolve(args.ledger),
            output_dir=resolve(args.output_dir),
            generation=args.generation,
        )
    )


if __name__ == "__main__":
    main()
