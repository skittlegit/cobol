"""Project exactly six accepted replacements across immutable review batches."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from cobol_archaeologist.benchmark.t6_replacement import (
    ReplacementBridgeManifest,
    ReplacementMultiBatchLedgerManifest,
    validate_replacement_batch_ledger,
    validate_replacement_bridge,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("replacement aggregate artifact escapes repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(),
        sha256=hashlib.sha256(resolved.read_bytes()).hexdigest(),
    )


def _write_once(path: Path, value: bytes) -> None:
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"refusing to overwrite replacement aggregate: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def build(*, root: Path, ledgers: list[Path], output_dir: Path) -> Path:
    root = root.resolve()
    accepted_by_pair = {}
    required_order = None
    batch_pins = []
    for ordinal, ledger_path in enumerate(ledgers):
        _, plans, accepted = validate_replacement_batch_ledger(
            root=root, ledger_path=ledger_path
        )
        if ordinal == 0:
            required_order = tuple(plan.rejected_pair_id for plan in plans)
        for plan, completion in accepted:
            if plan.rejected_pair_id in accepted_by_pair:
                raise ValueError("replacement aggregate has duplicate rejected-pair coverage")
            accepted_by_pair[plan.rejected_pair_id] = (plan, completion)
        batch_pins.append(_pin(root, ledger_path))
    if required_order is None or set(accepted_by_pair) != set(required_order):
        raise ValueError("replacement aggregate is not exact six-pair coverage")
    accepted = [accepted_by_pair[pair_id] for pair_id in required_order]
    if len(accepted) != 6:
        raise ValueError("replacement aggregate must project exactly six pairs")
    plans_path = output_dir / "accepted-plans.jsonl"
    responses_path = output_dir / "accepted-responses.jsonl"
    _write_once(
        plans_path,
        "".join(plan.model_dump_json() + "\n" for plan, _ in accepted).encode(
            "utf-8"
        ),
    )
    _write_once(
        responses_path,
        "".join(
            completion.model_dump_json() + "\n" for _, completion in accepted
        ).encode("utf-8"),
    )
    aggregate = ReplacementMultiBatchLedgerManifest(
        schema_version="1",
        ledger_variant="replacement_multi_batch_v1",
        finalized=True,
        batch_ledgers=tuple(batch_pins),
        required_rejected_pair_order=required_order,
        accepted_replacement_order=tuple(
            plan.replacement_id for plan, _ in accepted
        ),
        accepted_count=6,
    )
    aggregate_path = output_dir / "multi-batch-ledger-manifest.json"
    _write_once(
        aggregate_path,
        (aggregate.model_dump_json(indent=2) + "\n").encode("utf-8"),
    )
    bridge = ReplacementBridgeManifest(
        schema_version="1",
        finalized=True,
        projection="replacement_multibatch_to_t6_pool_v1",
        replacement_audit=_pin(root, aggregate_path),
        replacement_plan=_pin(root, plans_path),
        replacement_responses=_pin(root, responses_path),
        replacement_order=aggregate.accepted_replacement_order,
        review_item_members={
            plan.replacement_id: tuple(side.review_item_id for side in plan.sides)
            for plan, _ in accepted
        },
    )
    bridge_path = output_dir / "promotion-bridge-manifest.json"
    _write_once(
        bridge_path, (bridge.model_dump_json(indent=2) + "\n").encode("utf-8")
    )
    validate_replacement_bridge(root=root, bridge_path=bridge_path)
    return bridge_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--ledger", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    print(
        build(
            root=root,
            ledgers=[resolve(path) for path in args.ledger],
            output_dir=resolve(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
