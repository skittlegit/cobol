"""Build deterministic T6 promotion inputs from a finalized AI adjudication audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from cobol_archaeologist.benchmark.t6_adjudication_bridge import (
    build_ai_adjudication_promotion_bridge,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--release-policy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    bridge = build_ai_adjudication_promotion_bridge(
        root=root,
        audit_manifest_path=args.audit_manifest.resolve(),
        release_policy_path=args.release_policy.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    print(args.output_dir.resolve() / "promotion-bridge-manifest.json")
    print(bridge.adjudication_metadata.path)


if __name__ == "__main__":
    main()
