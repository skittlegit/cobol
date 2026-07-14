"""Command-line entry point for COBOL Archaeologist workflows."""

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "benchmark-build":  # pragma: no cover - argparse guards this
        return 2
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
