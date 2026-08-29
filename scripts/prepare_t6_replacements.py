"""Freeze additive replacement plans and proposal-blind model prompts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from cobol_archaeologist.benchmark.t6_pair_correction import (
    PairCorrectionAuditManifest,
)
from cobol_archaeologist.benchmark.t6_replacement import (
    REPLACEMENT_ORDER,
    ReplacementPlanItem,
    ReplacementSideInput,
    build_replacement_prompt,
    source_sha256,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    artifact_sha256_matches,
    load_candidate_pair_proposals,
)
from cobol_archaeologist.schemas import CodeLocus, SourceLocus


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("replacement artifact escapes repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=source_sha256(resolved)
    )


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"refusing to overwrite replacement artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _opaque(prefix: str, seed: str, length: int) -> str:
    return prefix + hashlib.sha256(seed.encode()).hexdigest()[:length]


def prepare(
    *,
    root: Path,
    output_dir: Path,
    protocol_version: Literal["v2_neutral", "v3_decision_semantics"] = "v2_neutral",
    freeze_version: Literal["v2", "v3", "v4"] = "v2",
) -> Path:
    root = root.resolve()
    correction_audit_path = (
        root
        / "data/benchmark/t6-v2/review/evidence/"
        "pair-aware-ai-correction/audit-manifest.json"
    )
    correction = PairCorrectionAuditManifest.model_validate_json(
        correction_audit_path.read_text(encoding="utf-8")
    )
    if correction.rejected_nonflip_count != 6:
        raise ValueError("replacement reserve requires six sealed rejected pairs")
    diagnostic_path = (
        root
        / "data/benchmark/t6-v2/replacements/review-v2/"
        "call-01.protocol-diagnostic.json"
    )
    diagnostic_pin: ArtifactPin | None = None
    if protocol_version == "v3_decision_semantics":
        diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        diagnostic_prompt = root / diagnostic["prompt"]["path"]
        if (
            not artifact_sha256_matches(
                diagnostic_prompt, diagnostic["prompt"]["sha256"]
            )
            or diagnostic["status"] != "rejected_protocol_semantics_ambiguous"
        ):
            raise ValueError("v3 protocol lineage diagnostic pin changed")
        diagnostic_pin = _pin(root, diagnostic_path)
    proposals = {
        pair.pair_id: pair
        for pair in load_candidate_pair_proposals(
            root / "data/benchmark/t6-v2/candidates/pair_proposals.jsonl"
        )
    }
    authority_pairs = [
        proposals["t6v2-candidate-01"].sides,
        proposals["t6v2-candidate-01"].sides,
        proposals["t6v2-candidate-01"].sides,
        proposals["t6v2-candidate-04"].sides,
        proposals["t6v2-candidate-04"].sides,
        proposals["t6v2-candidate-10"].sides,
    ]
    if protocol_version == "v2_neutral" and freeze_version != "v2":
        raise ValueError("neutral protocol is only valid for the immutable v2 freeze")
    if protocol_version == "v3_decision_semantics" and freeze_version == "v2":
        raise ValueError("decision-semantics protocol requires a post-v2 freeze")
    programs = (
        ("R3D", "R3B", "R3C", "R4A", "R4B", "R5A")
        if freeze_version in {"v3", "v4"}
        else ("R3A", "R3B", "R3C", "R4A", "R4B", "R5A")
    )
    first_program = (
        "CME6N5"
        if freeze_version in {"v3", "v4"}
        else "CMA7Q1"
    )
    public_loci = (
        ((first_program, "1000-MAIN", 9, None),),
        (
            ("CMB4K2", "1000-MAIN", 9, 18),
            ("CMH9P3", "2000-CHECK-ELIGIBILITY", 29, None),
        ),
        (("CMD8L4", "1000-MAIN", 9, None),),
        (("BOP7A1", "1000-MAIN", 9, None),),
        (
            ("BOP8B2", "1000-MAIN", 9, 17),
            ("BOH4C3", "2000-CLASSIFY-OWNER", 26, None),
        ),
        (
            ("KYC7A1", "1000-MAIN", 10, 19),
            ("KYC7A1", "2000-UPLOAD-REGISTRY", 20, None),
        ),
    )
    plans: list[ReplacementPlanItem] = []
    correction_sha = source_sha256(correction_audit_path)
    replacement_mapping = {}
    original_order = tuple(correction.pair_order)
    for ordinal, (replacement_id, suffix, locus_specs, proposal_sides) in enumerate(
        zip(REPLACEMENT_ORDER, programs, public_loci, authority_pairs, strict=True),
        start=1,
    ):
        source_path = (
            root
            / f"data/benchmark/t6-v2/replacements/programs/T6V2{suffix}.cbl"
        )
        source_text = source_path.read_text(encoding="utf-8")
        line_count = len(source_text.splitlines())
        locus = CodeLocus(
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
            is_interprocedural=len({spec[0] for spec in locus_specs}) > 1,
        )
        lineage_seed = (
            f"v4:{correction_sha}:{diagnostic_pin.sha256}:{replacement_id}"
            if freeze_version == "v4" and diagnostic_pin is not None
            else
            f"v3:{correction_sha}:{diagnostic_pin.sha256}:{replacement_id}"
            if diagnostic_pin is not None
            else f"{correction_sha}:{replacement_id}"
        )
        call_id = _opaque("rcall-", lineage_seed, 12)
        sides = sorted(proposal_sides, key=lambda side: side.candidate_side_id)
        if ordinal % 2 == 0:
            sides.reverse()
        replacement_mapping[replacement_id] = original_order[ordinal - 1]
        plans.append(
            ReplacementPlanItem(
                schema_version="1",
                replacement_id=replacement_id,
                rejected_pair_id=original_order[ordinal - 1],
                replacement_call_id=call_id,
                prompt_protocol_version=protocol_version,
                prior_protocol_diagnostic=diagnostic_pin,
                source=_pin(root, source_path),
                shared_source_text=source_text,
                code_locus=locus,
                host_design_note=(
                    "The complaint-month flag is a trusted upstream calendar-service "
                    "abstraction; this fixture tests escalation policy, not date math."
                    if suffix.startswith("R3")
                    else "The source directly implements the older authority behavior "
                    "while deliberately omitting only the later rule change."
                ),
                sides=tuple(
                    ReplacementSideInput(
                        position=position,
                        review_item_id=_opaque(
                            "rvw-",
                            (
                                f"v4:{diagnostic_pin.sha256}:"
                                f"{replacement_id}:{position}"
                                if freeze_version == "v4"
                                else f"{replacement_id}:{position}"
                            ),
                            8,
                        ),
                        source_alias=_opaque(
                            "src-",
                            (
                                f"v4:{diagnostic_pin.sha256}:"
                                f"{replacement_id}:{position}:source"
                                if freeze_version == "v4"
                                else f"{replacement_id}:{position}:source"
                            ),
                            12,
                        ),
                        authority=side.authority,
                    )
                    for position, side in zip(
                        ("alpha", "beta"), sides, strict=True
                    )
                ),
            )
        )
    plan_path = output_dir / "replacement-plan.coordinator-private.jsonl"
    _write_once(
        plan_path,
        "".join(plan.model_dump_json() + "\n" for plan in plans).encode("utf-8"),
    )
    calls = []
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
    )
    for ordinal, plan in enumerate(plans, start=1):
        prompt = build_replacement_prompt(plan)
        lowered = prompt.lower()
        if plan.replacement_id in prompt or any(word in lowered for word in forbidden):
            raise ValueError("replacement prompt leaks coordinator or outcome state")
        prompt_path = output_dir / "prompts" / f"replacement-{ordinal:02d}.txt"
        _write_once(prompt_path, prompt.encode("utf-8"))
        calls.append(
            {
                "replacement_id": plan.replacement_id,
                "replacement_call_id": plan.replacement_call_id,
                "review_item_order": [side.review_item_id for side in plan.sides],
                "prompt": _pin(root, prompt_path).model_dump(mode="json"),
                "prompt_utf8_length": len(prompt.encode("utf-8")),
            }
        )
    manifest_path = output_dir / "prompt-manifest.coordinator-private.json"
    manifest = {
        "schema_version": "1",
        "freeze_version": freeze_version,
        "model_id": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "fork_turns": "none",
        "tools_authorized": 0,
        "prior_pair_context_included": False,
        "correction_audit": _pin(root, correction_audit_path).model_dump(mode="json"),
        "replacement_plan": _pin(root, plan_path).model_dump(mode="json"),
        "replacement_order": list(REPLACEMENT_ORDER),
        "replacement_to_rejected_original": replacement_mapping,
        "calls": calls,
    }
    if diagnostic_pin is not None:
        manifest["prior_protocol_diagnostic"] = diagnostic_pin.model_dump(
            mode="json"
        )
    _write_once(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/benchmark/t6-v2/replacements/review-v4"),
    )
    parser.add_argument(
        "--protocol-version",
        choices=("v2_neutral", "v3_decision_semantics"),
        default="v3_decision_semantics",
    )
    parser.add_argument(
        "--freeze-version", choices=("v2", "v3", "v4"), default="v4"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = (
        args.output_dir.resolve()
        if args.output_dir.is_absolute()
        else (root / args.output_dir).resolve()
    )
    print(
        prepare(
            root=root,
            output_dir=output,
            protocol_version=args.protocol_version,
            freeze_version=args.freeze_version,
        )
    )


if __name__ == "__main__":
    main()
