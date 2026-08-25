"""Freeze the official configuration-3 collaboration smoke without running it."""

from __future__ import annotations

import argparse
from pathlib import Path

from cobol_archaeologist.eval.config3_prepare import (
    COLLABORATION_OUTPUT_DIR,
    prepare_config3_collaboration_smoke,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=COLLABORATION_OUTPUT_DIR,
    )
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_dir
    if not output.is_absolute():
        output = root / output
    plan = args.plan
    if plan is not None and not plan.is_absolute():
        plan = root / plan
    result = prepare_config3_collaboration_smoke(
        root=root,
        output_dir=output,
        plan_path=plan,
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
