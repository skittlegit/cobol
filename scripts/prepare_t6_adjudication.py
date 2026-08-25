"""Create a comparison report without adjudicating or promoting T6 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from cobol_archaeologist.benchmark.t6_comparison import (
    prepare_review_comparison,
    write_review_comparison,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--primary-transcript", type=Path, required=True)
    parser.add_argument("--independent-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare_review_comparison(
        root=args.root.resolve(),
        packet_path=args.packet.resolve(),
        primary_transcript_path=args.primary_transcript.resolve(),
        independent_manifest_path=args.independent_manifest.resolve(),
    )
    write_review_comparison(report, args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
