"""Frozen offline baselines and paired Phase-5 binary scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.benchmark.surface import (
    fit_surface_classifier,
    load_probe_rows,
    surface_features,
)
from cobol_archaeologist.eval.materialize import (
    MaterializedSource,
    materialize,
    materialize_base,
)
from cobol_archaeologist.rag.index import tokenize
from cobol_archaeologist.schemas import CurrentValue, DriftInstance, RegulationClause

RANDOM_IDENTITY = "m5-random-v1"
STATIC_KEYWORD_IDENTITY = "m5-static-keyword-v1"
SURFACE_ATTACKER_IDENTITY = "m5-attacker-with-bases-v1"
_NUMBER = re.compile(r"(?<![A-Z0-9-])[-+]?\d+(?:\.\d+)?", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "all",
    "an",
    "and",
    "as",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "shall",
    "that",
    "the",
    "to",
    "with",
}


class BinaryBaselineRecord(BaseModel):
    """One full-coverage binary prediction paired with frozen gold."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    system_id: str
    gold_is_drift: bool
    predicted_is_drift: bool
    score: float
    is_interprocedural: bool
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    details: dict = Field(default_factory=dict)


class OfflineBaselineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: str
    total: int
    split_sha256: str
    implementation_identity: str
    parameters: dict
    source_probe_sha256: str | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_source(source: MaterializedSource) -> str:
    return "\n".join(
        f"FILE {name}\n{content}" for name, content in sorted(source.files.items())
    )


def _leaf_values(node: CurrentValue) -> list[str]:
    if isinstance(node.value, dict):
        return [value for child in node.value.values() for value in _leaf_values(child)]
    if isinstance(node.value, list):
        return [str(value) for value in node.value]
    return [str(node.value)]


def static_keyword_score(clause: RegulationClause, source_text: str) -> float:
    """Return a label-free drift score from mandated values/content tokens."""

    upper = source_text.upper()
    if clause.current_value is not None:
        required = _leaf_values(clause.current_value)
        present = sum(
            bool(
                re.search(
                    rf"(?<![A-Z0-9-]){re.escape(value.upper())}(?![A-Z0-9-])",
                    upper,
                )
            )
            for value in required
        )
        return 1.0 - present / len(required)

    clause_tokens = [
        token
        for token in tokenize(clause.text)
        if token not in _STOPWORDS and len(token) >= 4 and not _NUMBER.fullmatch(token)
    ]
    if not clause_tokens:
        return 0.5
    source_tokens = set(tokenize(source_text))
    overlap = sum(token in source_tokens for token in set(clause_tokens))
    return 1.0 - min(1.0, overlap / min(3, len(set(clause_tokens))))


def _record(
    row: DriftInstance,
    *,
    system_id: str,
    predicted: bool,
    score: float,
    source_sha256: str,
    details: dict | None = None,
) -> BinaryBaselineRecord:
    return BinaryBaselineRecord(
        instance_id=row.instance_id,
        system_id=system_id,
        gold_is_drift=row.drift_type != "D7_conformant",
        predicted_is_drift=predicted,
        score=score,
        is_interprocedural=row.code_locus.is_interprocedural,
        source_sha256=source_sha256,
        details=details or {},
    )


def majority_baseline(
    train: list[DriftInstance],
    test: list[DriftInstance],
) -> list[BinaryBaselineRecord]:
    prevalence = sum(row.drift_type != "D7_conformant" for row in train) / len(train)
    predicted = prevalence >= 0.5
    return [
        _record(
            row,
            system_id="train_majority",
            predicted=predicted,
            score=prevalence,
            source_sha256=materialize(row).source_sha256,
            details={"train_drift_prevalence": prevalence},
        )
        for row in test
    ]


def prevalence_random_baseline(
    train: list[DriftInstance],
    test: list[DriftInstance],
) -> list[BinaryBaselineRecord]:
    prevalence = sum(row.drift_type != "D7_conformant" for row in train) / len(train)
    records = []
    for row in test:
        source = materialize(row)
        digest = hashlib.sha256(
            f"{RANDOM_IDENTITY}:{row.instance_id}".encode()
        ).digest()
        draw = int.from_bytes(digest[:8], "big") / 2**64
        records.append(
            _record(
                row,
                system_id="prevalence_random",
                predicted=draw < prevalence,
                score=prevalence,
                source_sha256=source.source_sha256,
                details={
                    "train_drift_prevalence": prevalence,
                    "identity": RANDOM_IDENTITY,
                },
            )
        )
    return records


def static_keyword_baseline(
    test: list[DriftInstance],
) -> list[BinaryBaselineRecord]:
    records = []
    for row in test:
        source = materialize(row)
        score = static_keyword_score(row.regulation_clause, _render_source(source))
        records.append(
            _record(
                row,
                system_id="static_keyword",
                predicted=score >= 0.5,
                score=score,
                source_sha256=source.source_sha256,
                details={"identity": STATIC_KEYWORD_IDENTITY, "threshold": 0.5},
            )
        )
    return records


def _surface_pair(
    base: MaterializedSource,
    current: MaterializedSource,
) -> tuple[str, str]:
    names = sorted(set(base.files) | set(current.files))
    before = "\n".join(f"FILE {name}\n{base.files.get(name, '')}" for name in names)
    after = "\n".join(f"FILE {name}\n{current.files.get(name, '')}" for name in names)
    return before, after


def surface_attacker_baseline(
    test: list[DriftInstance],
    *,
    probe_path: Path,
) -> tuple[list[BinaryBaselineRecord], OfflineBaselineManifest]:
    probe_rows = load_probe_rows(probe_path)
    classifier = fit_surface_classifier(probe_rows)
    records = []
    for row in test:
        base = materialize_base(row)
        current = materialize(row)
        before, after = _surface_pair(base, current)
        features = surface_features(before, after)
        raw_score = classifier.score(features)
        probability = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, raw_score))))
        records.append(
            _record(
                row,
                system_id="attacker_with_bases",
                predicted=classifier.predict(features) == 1,
                score=probability,
                source_sha256=current.source_sha256,
                details={
                    "identity": SURFACE_ATTACKER_IDENTITY,
                    "features": features,
                },
            )
        )
    manifest = OfflineBaselineManifest(
        system_id="attacker_with_bases",
        total=len(records),
        split_sha256="",
        implementation_identity=SURFACE_ATTACKER_IDENTITY,
        parameters={
            "feature_names": list(classifier.feature_names),
            "centers": classifier.centers,
            "scales": classifier.scales,
            "weights": classifier.weights,
            "bias": classifier.bias,
            "threshold": 0.0,
        },
        source_probe_sha256=_sha256(probe_path),
    )
    return records, manifest


def binary_detection(records: list[BinaryBaselineRecord]) -> dict:
    counts = Counter(
        (
            "tp"
            if row.gold_is_drift and row.predicted_is_drift
            else "fp"
            if not row.gold_is_drift and row.predicted_is_drift
            else "fn"
            if row.gold_is_drift
            else "tn"
        )
        for row in records
    )
    tp, fp, fn, tn = (counts[name] for name in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "answer_rate": 1.0,
    }


def write_binary_artifact(
    records: list[BinaryBaselineRecord],
    *,
    destination: Path,
    split_path: Path,
    manifest: OfflineBaselineManifest,
) -> None:
    ids = [row.instance_id for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("binary baseline artifact contains duplicate instance IDs")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(record.model_dump_json() + "\n" for record in records),
        encoding="utf-8",
    )
    manifest = manifest.model_copy(update={"split_sha256": _sha256(split_path)})
    destination.with_suffix(".manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def _load_split(path: Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_offline_suite(
    *,
    train_path: Path,
    test_path: Path,
    probe_path: Path,
    output_dir: Path,
) -> dict[str, dict]:
    """Write the four no-provider Phase-5 baselines and return their scores."""

    train = _load_split(train_path)
    test = _load_split(test_path)
    prevalence = sum(row.drift_type != "D7_conformant" for row in train) / len(train)
    majority = majority_baseline(train, test)
    random_records = prevalence_random_baseline(train, test)
    static = static_keyword_baseline(test)
    attacker, attacker_manifest = surface_attacker_baseline(
        test,
        probe_path=probe_path,
    )
    artifacts = {
        "train_majority": (
            majority,
            OfflineBaselineManifest(
                system_id="train_majority",
                total=len(test),
                split_sha256="",
                implementation_identity="m5-train-majority-v1",
                parameters={"train_drift_prevalence": prevalence},
            ),
        ),
        "prevalence_random": (
            random_records,
            OfflineBaselineManifest(
                system_id="prevalence_random",
                total=len(test),
                split_sha256="",
                implementation_identity=RANDOM_IDENTITY,
                parameters={"train_drift_prevalence": prevalence},
            ),
        ),
        "static_keyword": (
            static,
            OfflineBaselineManifest(
                system_id="static_keyword",
                total=len(test),
                split_sha256="",
                implementation_identity=STATIC_KEYWORD_IDENTITY,
                parameters={"threshold": 0.5},
            ),
        ),
        "attacker_with_bases": (attacker, attacker_manifest),
    }
    results = {}
    for name, (records, manifest) in artifacts.items():
        write_binary_artifact(
            records,
            destination=output_dir / f"{name}.jsonl",
            split_path=test_path,
            manifest=manifest,
        )
        results[name] = {
            "overall": binary_detection(records),
            "local": binary_detection(
                [row for row in records if not row.is_interprocedural]
            ),
            "interprocedural": binary_detection(
                [row for row in records if row.is_interprocedural]
            ),
        }
    (output_dir / "offline-summary.json").write_text(
        json.dumps(results, indent=2) + "\n",
        encoding="utf-8",
    )
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            build_offline_suite(
                train_path=args.train,
                test_path=args.test,
                probe_path=args.probe,
                output_dir=args.output_dir,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
