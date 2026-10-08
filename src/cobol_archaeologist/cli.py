"""Command-line entry point for benchmark generation and judging."""

from __future__ import annotations

import argparse
import json
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
    apply_verdicts,
    load_judgements,
    write_packets,
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
        "benchmark-build", help="generate the deterministic synthetic benchmark"
    )
    build.add_argument("--seed", type=int, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--min-instances", type=_positive_int, default=200)
    build.add_argument(
        "--diversify",
        choices=("deterministic", "llm"),
        default="deterministic",
    )
    packets = subcommands.add_parser(
        "benchmark-packets", help="write plausibility review packets for the judge"
    )
    packets.add_argument("--input", type=Path, required=True)
    packets.add_argument("--out", type=Path, required=True)
    apply = subcommands.add_parser(
        "benchmark-apply", help="keep rows the judge found plausible"
    )
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--judgements", type=Path, required=True)
    apply.add_argument("--accepted-out", type=Path, required=True)
    apply.add_argument("--rejected-out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "benchmark-build":
            result = build_benchmark(
                seed=args.seed,
                out_path=args.out,
                min_instances=args.min_instances,
                diversify_mode=args.diversify,
            )
            report = {
                "instances": result.manifest["instance_count"],
                "output": str(args.out),
                "manifest": str(manifest_path_for(args.out)),
            }
        elif args.command == "benchmark-packets":
            report = {
                "packets": write_packets(args.input, args.out),
                "out": str(args.out),
            }
        else:
            report = apply_verdicts(
                args.input,
                load_judgements(args.judgements),
                args.accepted_out,
                args.rejected_out,
            )
    except (BuildConfigurationError, FamilyIntegrityError, OSError, ValueError) as exc:
        print(f"{args.command}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
