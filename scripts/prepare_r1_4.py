"""Freeze R1.4 and prepare isolated qualification plus official smoke requests."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

from cobol_archaeologist.agent.adaptive import ADAPTIVE_SYSTEM_PROMPT
from cobol_archaeologist.eval.codex_batch import (
    CodexBaselineEnvelope,
    CodexBatchEnvelope,
    strict_codex_schema,
)
from cobol_archaeologist.eval.config3_live import (
    CodexAdaptiveEnvelope,
    Config3RunFreeze,
    build_adaptive_codex_prompt,
    build_agent_prompt,
    build_baseline_prompt,
)
from cobol_archaeologist.eval.config4_live import (
    CONFIG4_SYSTEMS,
    canonical_sha256,
    predeclare_config4,
)
from cobol_archaeologist.eval.config4_prepare import runtime_source_sha256
from cobol_archaeologist.eval.config4_runner import (
    load_config4_smoke_rows,
    prepare_config4_run,
)
from cobol_archaeologist.eval.run import repository_commit

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR = ROOT / "data/eval/legacy/m4-config3/lineage-v4/run-freeze-v2.json"
OUTPUT = ROOT / "data/eval/m4/global-smoke-lineage-3"
QUALIFICATION = ROOT / "data/eval/m4/global-qualification-3"


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _method_text(*paths: str) -> str:
    return json.dumps(
        {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in paths
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", choices=("gpt-5.6-luna", "gpt-6-luna"), default="gpt-5.6-luna")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--qualification", type=Path, default=QUALIFICATION)
    args = parser.parse_args()
    predecessor = Config3RunFreeze.model_validate_json(
        PREDECESSOR.read_text(encoding="utf-8")
    )
    prompt_builders = {
        "adaptive_agent": inspect.getsource(build_adaptive_codex_prompt)
        + ADAPTIVE_SYSTEM_PROMPT,
        "agent": inspect.getsource(build_agent_prompt),
        **{
            system_id: inspect.getsource(build_baseline_prompt) + system_id
            for system_id in CONFIG4_SYSTEMS
            if system_id not in {"agent", "adaptive_agent"}
        },
    }
    prompt_hashes = {
        system_id: _sha_text(text) for system_id, text in prompt_builders.items()
    }
    response_schema_hashes = {
        "adaptive_agent": canonical_sha256(strict_codex_schema(CodexAdaptiveEnvelope)),
        "agent": canonical_sha256(strict_codex_schema(CodexBatchEnvelope)),
        **{
            system_id: canonical_sha256(strict_codex_schema(CodexBaselineEnvelope))
            for system_id in CONFIG4_SYSTEMS
            if system_id not in {"agent", "adaptive_agent"}
        },
    }
    freeze, predeclaration = predeclare_config4(
        model_id=args.model_id,
        predecessor=predecessor,
        prompt_hashes=prompt_hashes,
        response_schema_hashes=response_schema_hashes,
        tool_policy=(
            "adaptive_agent: one opaque case per task, adaptive hunt only, at most "
            "16 calls; agent: frozen seven-hunt tools, at most 8 calls per hunt; "
            "plain_llm/rag_dense/rag_reranker/oracle_slice: no tools; exact finals "
            "are never edited or substituted"
        ),
        verifier_identity=_method_text(
            "src/cobol_archaeologist/model/verify.py",
            "src/cobol_archaeologist/agent/policy.py",
            "src/cobol_archaeologist/agent/adaptive.py",
        ),
        runner_identity=_method_text(
            "src/cobol_archaeologist/eval/config4_live.py",
            "src/cobol_archaeologist/eval/config4_runner.py",
            "src/cobol_archaeologist/eval/collaboration_transport.py",
            "src/cobol_archaeologist/eval/config3_controls.py",
            "src/cobol_archaeologist/eval/config3_live.py",
        ),
        repository_commit=repository_commit(ROOT),
        runtime_source_sha256_value=runtime_source_sha256(ROOT),
        batch_sizes={**predecessor.batch_sizes, "agent": 1},
        output_root=args.output,
        root=ROOT,
    )
    rows = load_config4_smoke_rows(freeze, root=ROOT)
    official = prepare_config4_run(
        freeze=freeze,
        rows=rows,
        mode="smoke",
        output_dir=args.output,
        root=ROOT,
    )
    qualification = prepare_config4_run(
        freeze=freeze,
        rows=rows,
        mode="smoke",
        output_dir=args.qualification,
        root=ROOT,
    )
    qualification_task = next(
        task for task in qualification.tasks if task.system_id == "agent"
    )
    receipt = {
        "freeze_sha256": canonical_sha256(freeze),
        "predeclaration_sha256": canonical_sha256(predeclaration),
        "runtime_source_sha256": freeze.runtime_source_sha256,
        "official_task_count": official.task_count,
        "qualification_task": qualification_task.model_dump(mode="json"),
    }
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
