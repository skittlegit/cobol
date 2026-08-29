"""Prepare provider-free configuration-4 adaptive train/dev tasks."""

from __future__ import annotations

import argparse
from pathlib import Path

from cobol_archaeologist.eval.config4_prepare import (
    DEFAULT_CASE_LIMIT,
    OUTPUT_DIR,
    prepare_config4_adaptive_dev,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--selection", choices=("dev", "train", "train-dev"), default="dev"
    )
    parser.add_argument("--row-id", action="append", dest="row_ids")
    parser.add_argument("--limit", type=int, default=DEFAULT_CASE_LIMIT)
    parser.add_argument("--trial-id", default="trial-01")
    parser.add_argument("--max-workers", type=int, default=3)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_dir
    if not output.is_absolute():
        output = root / output
    result = prepare_config4_adaptive_dev(
        root=root,
        output_dir=output,
        selection=args.selection,
        row_ids=args.row_ids,
        limit=args.limit,
        trial_id=args.trial_id,
        max_workers=args.max_workers,
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

