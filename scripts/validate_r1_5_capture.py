"""Validate an R1.5 final capture without mutating or scoring it."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from cobol_archaeologist.eval.config4_runner import _response_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", required=True)
    parser.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args()
    raw = args.capture.read_bytes()
    _response_model(args.system).model_validate_json(raw)
    print(f"VALID {hashlib.sha256(raw).hexdigest()} {args.capture}")


if __name__ == "__main__":
    main()
