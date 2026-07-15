"""Command-line entry point for COBOL Archaeologist workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from cobol_archaeologist.benchmark.build import (
    BuildConfigurationError,
    build_benchmark,
    manifest_path_for,
)
from cobol_archaeologist.benchmark.judge import (
    FamilyIntegrityError,
    JudgeConfig,
    JudgeConfigurationError,
    apply_drop_policy,
    judge_benchmark,
    load_judgements,
    load_unsure_adjudications,
    record_human_agreement,
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cobol-archaeologist")
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser(
        "benchmark-build", help="generate deterministic synthetic benchmark v1"
    )
    build.add_argument("--seed", type=int, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--min-instances", type=_positive_int, default=200)
    build.add_argument(
        "--diversify",
        choices=("deterministic", "llm"),
        default="deterministic",
    )
    judge = subcommands.add_parser(
        "benchmark-judge", help="judge synthetic instances for legacy plausibility"
    )
    judge.add_argument(
        "--input", type=Path, default=Path("data/benchmark/drift_instances.jsonl")
    )
    judge.add_argument(
        "--out", type=Path, default=Path("data/benchmark/judgements.jsonl")
    )
    judge.add_argument("--sample", type=_positive_int)
    judge.add_argument("--seed", type=int, default=2400)
    judge.add_argument("--model")
    judge.add_argument("--model-family")
    judge.add_argument(
        "--reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
    )
    judge.add_argument("--endpoint")
    judge.add_argument("--api-key-env", default="OPENAI_API_KEY")
    judge.add_argument("--accepted-out", type=Path)
    judge.add_argument("--rejected-dir", type=Path)
    judge.add_argument(
        "--reuse-judgements",
        type=Path,
        help="reuse matching model verdicts by instance ID from an earlier JSONL",
    )
    judge.add_argument(
        "--human-review",
        type=Path,
        help="record exactly 15 human review rows against an existing output",
    )
    judge.add_argument(
        "--adjudications",
        type=Path,
        help="apply human plausible/implausible decisions to all unsure rows",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "benchmark-build":
        try:
            result = build_benchmark(
                seed=args.seed,
                out_path=args.out,
                min_instances=args.min_instances,
                diversify_mode=args.diversify,
            )
        except BuildConfigurationError as exc:
            print(f"benchmark-build: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "instances": result.manifest["instance_count"],
                    "output": str(args.out),
                    "manifest": str(manifest_path_for(args.out)),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "benchmark-judge":
        manifest_path = manifest_path_for(args.input)
        if args.human_review is not None:
            try:
                report = record_human_agreement(
                    args.out, args.human_review, manifest_path
                )
            except (OSError, ValueError) as exc:
                print(f"benchmark-judge: {exc}", file=sys.stderr)
                return 2
            print(json.dumps({"human_agreement": report}, sort_keys=True))
            return 0
        if args.adjudications is not None:
            try:
                accepted = args.accepted_out or args.input.with_name(
                    f"{args.input.stem}.plausible.jsonl"
                )
                rejected = args.rejected_dir or args.input.parent / "rejected"
                decisions = load_unsure_adjudications(args.adjudications)
                report = apply_drop_policy(
                    args.input,
                    load_judgements(args.out),
                    accepted,
                    rejected,
                    decisions,
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest.setdefault("judging", {})["unsure_adjudication"] = {
                    "file": str(args.adjudications),
                    "reviewed": len(decisions),
                    "accepted": sum(
                        item.verdict == "plausible" for item in decisions
                    ),
                    "rejected": sum(
                        item.verdict == "implausible" for item in decisions
                    ),
                }
                manifest_path.write_text(
                    json.dumps(
                        manifest, ensure_ascii=False, indent=2, sort_keys=True
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except (OSError, ValueError) as exc:
                print(f"benchmark-judge: {exc}", file=sys.stderr)
                return 2
            print(json.dumps({"drop_policy": report}, sort_keys=True))
            return 0

        model = args.model or os.environ.get("OPENAI_MODEL", "")
        family = args.model_family or os.environ.get("JUDGE_MODEL_FAMILY", "")
        reasoning_effort = args.reasoning_effort or os.environ.get(
            "OPENAI_REASONING_EFFORT"
        )
        endpoint = args.endpoint or os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        api_key = os.environ.get(args.api_key_env, "")
        if not api_key:
            print(
                f"benchmark-judge: {args.api_key_env} is required; refusing unauthenticated judging",
                file=sys.stderr,
            )
            return 2
        if not model or not family:
            print(
                "benchmark-judge: --model and --model-family (or env equivalents) are required",
                file=sys.stderr,
            )
            return 2
        try:
            report = judge_benchmark(
                instances_path=args.input,
                output_path=args.out,
                config=JudgeConfig(
                    endpoint=endpoint,
                    api_key=api_key,
                    model=model,
                    model_family=family,
                    reasoning_effort=reasoning_effort,
                ),
                sample=args.sample,
                seed=args.seed,
                reuse_path=args.reuse_judgements,
            )
            if args.sample is None:
                accepted = args.accepted_out or args.input.with_name(
                    f"{args.input.stem}.plausible.jsonl"
                )
                rejected = args.rejected_dir or args.input.parent / "rejected"
                report["drop_policy"] = apply_drop_policy(
                    args.input, load_judgements(args.out), accepted, rejected
                )
        except (
            FamilyIntegrityError,
            JudgeConfigurationError,
            OSError,
            ValueError,
        ) as exc:
            print(f"benchmark-judge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, sort_keys=True))
        return 0 if report["gate_passed"] else 1

    return 2  # pragma: no cover - argparse requires a known subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
