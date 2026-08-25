"""Replay sealed configuration-3 collaboration control bundles on the host."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from cobol_archaeologist.eval import config3_live
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationSubagentRequest,
)
from cobol_archaeologist.eval.config3_controls import run_config3_control
from cobol_archaeologist.eval.config3_live import (
    Config3RunFreeze,
    canonical_sha256,
    run_config3_adaptive,
)
from cobol_archaeologist.eval.config3_prepare import _smoke_rows
from cobol_archaeologist.model.verify import LexicalEntailer


def _install_collaboration_readiness_resolver(output_dir: Path) -> None:
    """Resolve deep-validation hashes from the frozen collaboration requests.

    The legacy deep readiness validator reconstructs Codex CLI request hashes.
    A collaboration freeze intentionally has no Codex binary, so use the
    self-validating request-v2 artifacts instead. Non-empty source rosters and
    authorized hunts uniquely identify agent/adaptive requests; source-free
    baseline requests additionally bind the exact prompt hash.
    """

    requests = [
        CollaborationSubagentRequest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        for directory in ("requests-v2", "requests-v3")
        for path in sorted((output_dir / "smoke").glob(f"*/{directory}/*.json"))
    ]
    if not requests:
        raise RuntimeError("no frozen collaboration requests are available")

    def resolve(**kwargs: Any) -> str:
        if kwargs.get("transport") != "collaboration_subagent":
            return config3_live.expected_codex_request_sha256(**kwargs)
        sources = kwargs["sources"]
        source_sha256 = {
            alias: source.source_sha256 for alias, source in sorted(sources.items())
        }
        prompt_sha256 = hashlib.sha256(kwargs["prompt"].encode("utf-8")).hexdigest()
        schema_sha256 = canonical_sha256(kwargs["schema"])
        authorized_hunts = tuple(kwargs["authorized_hunts"])
        matches = [
            request
            for request in requests
            if request.source_sha256 == source_sha256
            and request.schema_sha256 == schema_sha256
            and request.runtime_source_sha256 == kwargs["runtime_source_sha256"]
            and request.authorized_hunts == authorized_hunts
            and (source_sha256 or request.prompt_sha256 == prompt_sha256)
        ]
        if len(matches) != 1:
            raise RuntimeError(
                "frozen collaboration request identity is missing or ambiguous"
            )
        return matches[0].request_sha256

    original = config3_live.expected_codex_request_sha256

    def guarded_resolve(**kwargs: Any) -> str:
        if kwargs.get("transport") == "collaboration_subagent":
            return resolve(**kwargs)
        return original(**kwargs)

    config3_live.expected_codex_request_sha256 = guarded_resolve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "system",
        choices=(
            "agent",
            "adaptive_agent",
            "plain_llm",
            "rag_dense",
            "rag_reranker",
            "oracle_slice",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/eval/m4-config3/lineage-v4"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    freeze = Config3RunFreeze.model_validate_json(
        (output_dir / "run-freeze-v2.json").read_text(encoding="utf-8")
    )
    _install_collaboration_readiness_resolver(output_dir)
    rows = _smoke_rows(freeze, root=root)
    if args.system == "adaptive_agent":
        records, progress = run_config3_adaptive(
            rows=rows,
            mode="smoke",
            freeze=freeze,
            output_dir=output_dir,
            max_workers=freeze.max_workers,
            transport="collaboration_subagent",
            entailer=LexicalEntailer(),
        )
    else:
        records, progress = run_config3_control(
            args.system,
            rows=rows,
            mode="smoke",
            freeze=freeze,
            output_dir=output_dir,
            max_workers=freeze.max_workers,
            transport="collaboration_subagent",
            entailer=LexicalEntailer(),
        )
    print(progress.model_dump_json(indent=2))
    print(f"records={len(records)}")


if __name__ == "__main__":
    main()
