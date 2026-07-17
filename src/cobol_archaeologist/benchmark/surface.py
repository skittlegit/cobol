"""Deterministic surface diversification and T2.2 anti-gaming features."""

from __future__ import annotations

import difflib
import json
import math
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean


FEATURE_NAMES = (
    "diff_size",
    "touched_line_count",
    "comment_density_delta",
    "identifier_entropy_delta",
    "literal_roundness",
    "whitespace_churn",
)

_COMMENT_RE = re.compile(r"^.{6}[*/]", re.ASCII)
_IDENTIFIER_RE = re.compile(r"\b(?:WS|LK)-[A-Z0-9-]+\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<![A-Z0-9-])\d+(?:\.\d+)?", re.IGNORECASE)
_DISPLAY_RE = re.compile(r"(\bDISPLAY\s+)'([^']*)'", re.IGNORECASE)
_SYNONYMS = (
    ("CHECK", "VERIFY"),
    ("VALIDATION", "CHECKING"),
    ("CUSTOMER", "CLIENT"),
    ("ACCOUNT", "ACCT"),
    ("CALCULATE", "COMPUTE"),
    ("UPDATED", "REVISED"),
    ("PROCESSOR", "HANDLER"),
    ("IDENTIFICATION", "DETECTION"),
)


@dataclass(frozen=True)
class SurfaceEdit:
    kind: str
    line: int
    old: str
    new: str


@dataclass(frozen=True)
class ProbeRow:
    label: int
    base_program: str
    operator: str
    features: dict[str, float]
    source_hash: str


@dataclass(frozen=True)
class ProbeReport:
    auc: float
    ci_low: float
    ci_high: float
    samples: int


def _line_bounds(lines: list[str], region: tuple[int, int] | None) -> range:
    if not lines:
        return range(0)
    if region is None:
        return range(len(lines))
    start, end = region
    return range(max(0, start - 1), min(len(lines), end))


def _join_like(source: str, lines: list[str]) -> str:
    ending = "\n" if source.endswith(("\n", "\r")) else ""
    return "\n".join(lines) + ending


def _reword_comment(line: str, rng: random.Random) -> str:
    upper = line.upper()
    for old, new in _SYNONYMS:
        match = re.search(rf"\b{old}\b", upper)
        if match:
            rewritten = line[: match.start()] + new + line[match.end() :]
            return rewritten.rstrip() + (" " * (1 + rng.randrange(4)))
    if line.rstrip().endswith("-"):
        return line.rstrip()[:-1] + "=" + (" " * rng.randrange(4))
    return line.rstrip() + (" " * (1 + rng.randrange(4)))


def diversify_with_edits(
    source: str,
    region: tuple[int, int] | None,
    rng: random.Random,
) -> tuple[str, tuple[SurfaceEdit, ...]]:
    """Apply a deterministic, line-count-preserving surface pass.

    The gate implementation uses comment rewording first because comments are
    semantically inert in fixed-format COBOL. Sources without comments receive
    trailing-whitespace variation, which is also ignored by the compiler.
    Richer catalogue helpers below are available to the scale builder.
    """

    lines = source.splitlines()
    candidates = [
        index
        for index in _line_bounds(lines, region)
        if _COMMENT_RE.match(lines[index])
    ]
    if not candidates:
        candidates = [
            index for index, line in enumerate(lines) if _COMMENT_RE.match(line)
        ]
    if not candidates:
        candidates = [index for index in _line_bounds(lines, region) if lines[index]]
    if not candidates:
        candidates = [index for index, line in enumerate(lines) if line]
    if not candidates:
        return source, ()

    index = candidates[rng.randrange(len(candidates))]
    old = lines[index]
    new = (
        _reword_comment(old, rng)
        if _COMMENT_RE.match(old)
        else old.rstrip() + (" " * (1 + rng.randrange(4)))
    )
    if new == old:
        new += " "
    lines[index] = new
    edit = SurfaceEdit(
        kind="comment_reword" if _COMMENT_RE.match(old) else "whitespace",
        line=index + 1,
        old=old,
        new=new,
    )
    return _join_like(source, lines), (edit,)


def diversify(
    source: str,
    region: tuple[int, int] | None,
    rng: random.Random | None = None,
) -> str:
    """Public pluggable diversification pass required by the work order."""

    diversified, _ = diversify_with_edits(source, region, rng or random.Random(0))
    return diversified


def rename_nonregulated_identifier(
    source: str,
    protected: set[str],
    rng: random.Random,
) -> tuple[str, tuple[SurfaceEdit, ...]]:
    """Rename one WS/LK identifier everywhere without touching PIC/USAGE."""

    protected_upper = {item.upper() for item in protected}
    identifiers = sorted(
        {
            match.group(0).upper()
            for match in _IDENTIFIER_RE.finditer(source)
            if match.group(0).upper() not in protected_upper
        }
    )
    if not identifiers:
        return source, ()
    old = identifiers[rng.randrange(len(identifiers))]
    new = f"WS-SURF-{rng.randrange(1000, 10000)}"
    pattern = re.compile(rf"\b{re.escape(old)}\b", re.IGNORECASE)
    changed_lines: list[SurfaceEdit] = []
    lines = source.splitlines()
    for index, line in enumerate(lines):
        replaced = pattern.sub(new, line)
        if replaced != line:
            changed_lines.append(
                SurfaceEdit("identifier_rename", index + 1, line, replaced)
            )
            lines[index] = replaced
    return _join_like(source, lines), tuple(changed_lines)


def perturb_nonregulated_literal(
    source: str,
    protected_values: set[str],
    rng: random.Random,
) -> tuple[str, tuple[SurfaceEdit, ...]]:
    """Change one display string or unprotected cosmetic numeric literal."""

    lines = source.splitlines()
    display_lines = [
        index for index, line in enumerate(lines) if _DISPLAY_RE.search(line)
    ]
    if display_lines:
        index = display_lines[rng.randrange(len(display_lines))]
        old = lines[index]

        def repl(match: re.Match[str]) -> str:
            value = match.group(2)
            if ":" in value:
                replacement = value.replace(":", "=", 1)
            elif value.endswith(" "):
                replacement = value.rstrip() + "  "
            else:
                replacement = value + " "
            return f"{match.group(1)}'{replacement}'"

        new = _DISPLAY_RE.sub(repl, old, count=1)
        lines[index] = new
        return _join_like(source, lines), (
            SurfaceEdit("display_literal", index + 1, old, new),
        )

    protected = {str(value) for value in protected_values}
    candidates: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        if _COMMENT_RE.match(line):
            continue
        for match in _NUMBER_RE.finditer(line):
            if match.group(0) not in protected:
                candidates.append((index, match))
    if not candidates:
        return source, ()
    index, match = candidates[rng.randrange(len(candidates))]
    old = lines[index]
    value = match.group(0)
    replacement = str(int(value) + 1) if value.isdigit() else value
    new = old[: match.start()] + replacement + old[match.end() :]
    lines[index] = new
    return _join_like(source, lines), (
        SurfaceEdit("cosmetic_literal", index + 1, old, new),
    )


def reorder_independent_paragraphs(
    source: str,
    rng: random.Random,
) -> tuple[str, tuple[SurfaceEdit, ...]]:
    """Reorder two uncalled paragraphs only when textual dependencies are absent.

    This conservative helper refuses GO TO/THRU and only moves paragraph blocks
    appearing after a STOP RUN, so ordinary fall-through cannot reach them.
    """

    if re.search(r"\b(?:GO\s+TO|THRU)\b", source, re.IGNORECASE):
        return source, ()
    lines = source.splitlines()
    stop = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"\bSTOP\s+RUN\b", line, re.IGNORECASE)
        ),
        None,
    )
    if stop is None:
        return source, ()
    header = re.compile(r"^\s{7}([A-Z0-9][A-Z0-9-]*)\.\s*$", re.IGNORECASE)
    starts = [
        index for index in range(stop + 1, len(lines)) if header.match(lines[index])
    ]
    if len(starts) < 2:
        return source, ()
    first_index = rng.randrange(len(starts) - 1)
    a = starts[first_index]
    b = starts[first_index + 1]
    c = starts[first_index + 2] if first_index + 2 < len(starts) else len(lines)
    first, second = lines[a:b], lines[b:c]
    if any(
        re.search(
            rf"\bPERFORM\s+{re.escape(header.match(block[0]).group(1))}\b",
            source,
            re.IGNORECASE,
        )
        for block in (first, second)
    ):
        return source, ()
    lines[a:c] = second + first
    return _join_like(source, lines), (
        SurfaceEdit(
            "paragraph_reorder",
            a + 1,
            "\n".join(first + second),
            "\n".join(second + first),
        ),
    )


def _changed_line_pairs(before: str, after: str) -> list[tuple[str, str]]:
    left, right = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    pairs: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        width = max(i2 - i1, j2 - j1)
        for offset in range(width):
            old = left[i1 + offset] if i1 + offset < i2 else ""
            new = right[j1 + offset] if j1 + offset < j2 else ""
            pairs.append((old, new))
    return pairs


def _comment_density(source: str) -> float:
    lines = source.splitlines()
    return sum(bool(_COMMENT_RE.match(line)) for line in lines) / max(1, len(lines))


def _identifier_entropy(source: str) -> float:
    identifiers = [match.group(0).upper() for match in _IDENTIFIER_RE.finditer(source)]
    if not identifiers:
        return 0.0
    counts = {item: identifiers.count(item) for item in set(identifiers)}
    total = len(identifiers)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _roundness(lines: list[str]) -> float:
    values: list[float] = []
    for line in lines:
        if _COMMENT_RE.match(line):
            continue
        values.extend(float(match.group(0)) for match in _NUMBER_RE.finditer(line))
    if not values:
        return 0.0
    round_values = sum(value == 0 or value % 5 == 0 for value in values)
    return round_values / len(values)


def surface_features(before: str, after: str) -> dict[str, float]:
    """Extract the six surface-only probe features named by the work order."""

    pairs = _changed_line_pairs(before, after)
    diff_size = sum(
        max(len(old), len(new))
        - int(
            difflib.SequenceMatcher(a=old, b=new, autojunk=False).ratio()
            * max(len(old), len(new))
        )
        for old, new in pairs
    )
    whitespace = sum(
        abs(sum(char.isspace() for char in old) - sum(char.isspace() for char in new))
        for old, new in pairs
    )
    values = {
        "diff_size": float(diff_size),
        "touched_line_count": float(len(pairs)),
        "comment_density_delta": abs(
            _comment_density(after) - _comment_density(before)
        ),
        "identifier_entropy_delta": abs(
            _identifier_entropy(after) - _identifier_entropy(before)
        ),
        "literal_roundness": _roundness(after.splitlines()),
        "whitespace_churn": float(whitespace),
    }
    return {name: values[name] for name in FEATURE_NAMES}


def load_probe_rows(path: str | Path) -> list[ProbeRow]:
    rows: list[ProbeRow] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        features = {name: float(raw["features"][name]) for name in FEATURE_NAMES}
        label = int(raw["label"])
        if label not in (0, 1):
            raise ValueError(f"probe row {line_number}: label must be 0/1")
        rows.append(
            ProbeRow(
                label=label,
                base_program=str(raw["base_program"]),
                operator=str(raw["operator"]),
                features=features,
                source_hash=str(raw["source_hash"]),
            )
        )
    return rows


def dump_probe_rows(rows: list[ProbeRow], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        json.dumps(asdict(row), sort_keys=False, separators=(",", ":")) for row in rows
    )
    target.write_text(text + "\n", encoding="utf-8")


def _standardize(matrix: list[list[float]]) -> list[list[float]]:
    columns = list(zip(*matrix, strict=True))
    centers = [mean(column) for column in columns]
    scales = [
        math.sqrt(mean((value - center) ** 2 for value in column)) or 1.0
        for column, center in zip(columns, centers, strict=True)
    ]
    return [
        [
            (value - center) / scale
            for value, center, scale in zip(row, centers, scales, strict=True)
        ]
        for row in matrix
    ]


def _train_logistic(
    matrix: list[list[float]], labels: list[int]
) -> tuple[list[float], float]:
    weights = [0.0] * len(matrix[0])
    bias = 0.0
    count = len(matrix)
    for _ in range(500):
        grad_w = [0.0] * len(weights)
        grad_b = 0.0
        for row, label in zip(matrix, labels, strict=True):
            score = max(
                -30.0,
                min(30.0, bias + sum(w * x for w, x in zip(weights, row, strict=True))),
            )
            error = 1.0 / (1.0 + math.exp(-score)) - label
            for index, value in enumerate(row):
                grad_w[index] += error * value
            grad_b += error
        for index in range(len(weights)):
            weights[index] -= 0.15 * (grad_w[index] / count + 0.02 * weights[index])
        bias -= 0.15 * grad_b / count
    return weights, bias


def _auc(labels: list[int], scores: list[float]) -> float:
    positive = [
        score for label, score in zip(labels, scores, strict=True) if label == 1
    ]
    negative = [
        score for label, score in zip(labels, scores, strict=True) if label == 0
    ]
    if not positive or not negative:
        return 0.5
    wins = sum(
        1.0 if pos > neg else 0.5 if pos == neg else 0.0
        for pos in positive
        for neg in negative
    )
    return wins / (len(positive) * len(negative))


def per_feature_auc(rows: list[ProbeRow]) -> dict[str, float]:
    """Single-feature AUC for each probe feature, drift vs conformant.

    0.5 is chance. Reported alongside the aggregate because an aggregate alone
    cannot say whether the probe is riding one leaky axis or many, and the
    datasheet's anti-gaming claim should be falsifiable per feature.
    """

    scores: dict[str, float] = {}
    for name in FEATURE_NAMES:
        pos = [row.features[name] for row in rows if row.label == 1]
        neg = [row.features[name] for row in rows if row.label == 0]
        if not pos or not neg:
            scores[name] = float("nan")
            continue
        wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
        scores[name] = round(wins / (len(pos) * len(neg)), 5)
    return scores


def surface_probe_report(
    rows: list[ProbeRow],
    *,
    seed: int,
    bootstrap_samples: int = 1000,
) -> ProbeReport:
    """Fit a deterministic logistic probe and bootstrap its AUC predictions."""

    if len(rows) < 4 or {row.label for row in rows} != {0, 1}:
        raise ValueError("surface probe requires both labels and at least four rows")
    matrix = _standardize(
        [[row.features[name] for name in FEATURE_NAMES] for row in rows]
    )
    labels = [row.label for row in rows]
    weights, bias = _train_logistic(matrix, labels)
    scores = [
        bias + sum(w * x for w, x in zip(weights, row, strict=True)) for row in matrix
    ]
    auc = _auc(labels, scores)

    rng = random.Random(seed)
    pos = [index for index, label in enumerate(labels) if label == 1]
    neg = [index for index, label in enumerate(labels) if label == 0]
    bootstrapped: list[float] = []
    for _ in range(bootstrap_samples):
        indices = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
        bootstrapped.append(
            _auc([labels[i] for i in indices], [scores[i] for i in indices])
        )
    bootstrapped.sort()
    low_index = max(0, int(0.025 * len(bootstrapped)) - 1)
    high_index = min(len(bootstrapped) - 1, int(0.975 * len(bootstrapped)))
    return ProbeReport(
        auc=auc,
        ci_low=bootstrapped[low_index],
        ci_high=bootstrapped[high_index],
        samples=len(rows),
    )
