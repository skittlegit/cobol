"""Freeze exactly the reserve calls derived from a sealed failed-attempt ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

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
        raise ValueError("reserve artifact escapes repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=source_sha256(resolved)
    )


def _write_once(path: Path, value: bytes) -> None:
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"refusing to overwrite frozen reserve artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _opaque(prefix: str, seed: str, length: int) -> str:
    return prefix + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def prepare(*, root: Path, ledger_path: Path, output_dir: Path) -> Path:
    root = root.resolve()
    ledger, base_plans, accepted = validate_replacement_batch_ledger(
        root=root, ledger_path=ledger_path
    )
    accepted_ids = {plan.replacement_id for plan, _ in accepted}
    missing = [plan for plan in base_plans if plan.replacement_id not in accepted_ids]
    if len(missing) != 2:
        raise ValueError("reserve-v1 requires exactly two ledger-derived gaps")
    source_specs = {
        "t6v2-candidate-02": (
            "R3E",
            (("CMF2R7", "1000-MAIN", 9, None),),
            (
                "The complaint-month flag is a trusted upstream calendar-service "
                "abstraction; this fixture tests escalation policy, not date math."
            ),
        ),
        "t6v2-candidate-05": (
            "R4C",
            (("BOC6D4", "1000-MAIN", 9, None),),
            (
                "The source directly implements the older authority behavior while "
                "deliberately omitting only the later rule change."
            ),
        ),
    }
    if {plan.rejected_pair_id for plan in missing} != set(source_specs):
        raise ValueError("reserve-v1 gap families differ from sealed v4 outcomes")
    ledger_pin = _pin(root, ledger_path)
    plans: list[ReplacementPlanItem] = []
    replacement_ids = ("t6v2-replacement-07", "t6v2-replacement-08")
    for ordinal, (replacement_id, rejected) in enumerate(
        zip(replacement_ids, missing, strict=True), start=1
    ):
        suffix, locus_specs, note = source_specs[rejected.rejected_pair_id]
        source_path = (
            root
            / f"data/benchmark/t6-v2/replacements/programs/T6V2{suffix}.cbl"
        )
        source_text = source_path.read_text(encoding="utf-8")
        line_count = len(source_text.splitlines())
        lineage = f"reserve-v1:{ledger_pin.sha256}:{replacement_id}"
        authorities = list(rejected.sides)
        authorities.reverse()
        plans.append(
            ReplacementPlanItem(
                schema_version="1",
                replacement_id=replacement_id,
                rejected_pair_id=rejected.rejected_pair_id,
                replacement_call_id=_opaque("rcall-", lineage, 12),
                prompt_protocol_version="v3_decision_semantics",
                prior_protocol_diagnostic=rejected.prior_protocol_diagnostic,
                prior_batch_ledger=ledger_pin,
                source=_pin(root, source_path),
                shared_source_text=source_text,
                code_locus=CodeLocus(
                    loci=tuple(
                        SourceLocus(
                            program=program,
                            paragraph=paragraph,
                            file=None,
                            line_span=(start, end or line_count),
                        )
                        for program, paragraph, start, end in locus_specs
                    ),
                    slice_vars=(),
                    is_interprocedural=len(locus_specs) > 1,
                ),
                host_design_note=note,
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
                    for position, side in zip(
                        ("alpha", "beta"), authorities, strict=True
                    )
                ),
            )
        )
    plan_path = output_dir / "replacement-plan.coordinator-private.jsonl"
    _write_once(
        plan_path,
        "".join(plan.model_dump_json() + "\n" for plan in plans).encode("utf-8"),
    )
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
    calls = []
    for ordinal, plan in enumerate(plans, start=1):
        prompt = build_replacement_prompt(plan).encode("utf-8")
        lowered = prompt.decode("utf-8").lower()
        if any(token in lowered for token in forbidden):
            raise ValueError("reserve prompt leaks coordinator or expected outcome")
        prompt_path = output_dir / "prompts" / f"reserve-{ordinal:02d}.txt"
        _write_once(prompt_path, prompt)
        calls.append(
            {
                "replacement_id": plan.replacement_id,
                "replacement_call_id": plan.replacement_call_id,
                "review_item_order": [side.review_item_id for side in plan.sides],
                "prompt": _pin(root, prompt_path).model_dump(mode="json"),
                "prompt_utf8_length": len(prompt),
            }
        )
    manifest = {
        "schema_version": "1",
        "freeze_version": "reserve-v1",
        "model_id": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "fork_turns": "none",
        "tools_authorized": 0,
        "prior_pair_context_included": False,
        "correction_audit": ledger.correction_audit.model_dump(mode="json"),
        "prior_batch_ledger": ledger_pin.model_dump(mode="json"),
        "replacement_plan": _pin(root, plan_path).model_dump(mode="json"),
        "replacement_order": list(replacement_ids),
        "replacement_to_rejected_original": {
            plan.replacement_id: plan.rejected_pair_id for plan in plans
        },
        "calls": calls,
    }
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
            "data/benchmark/t6-v2/replacements/evidence/review-v4-ledger/"
            "batch-ledger-manifest.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/benchmark/t6-v2/replacements/review-reserve-v1"),
    )
    args = parser.parse_args()
    root = args.root.resolve()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    print(prepare(root=root, ledger_path=resolve(args.ledger), output_dir=resolve(args.output_dir)))


if __name__ == "__main__":
    main()
