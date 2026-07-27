from pathlib import Path

from cobol_archaeologist.benchmark.surface import (
    FEATURE_NAMES,
    fit_surface_classifier,
    load_probe_rows,
    surface_probe_report,
)

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "data" / "benchmark" / "probes" / "t2.2_surface_probe.jsonl"


def test_registered_surface_classifier_reproduces_probe_predictions():
    rows = load_probe_rows(PROBE)
    classifier = fit_surface_classifier(rows)
    assert classifier.feature_names == FEATURE_NAMES
    report = surface_probe_report(rows, seed=2601, bootstrap_samples=200)
    assert report.auc == 0.5
    by_base = {}
    for row in rows:
        by_base.setdefault(row.base_program, []).append(row)
    assert all(
        len({classifier.score(row.features) for row in paired}) == 1
        for paired in by_base.values()
    )


def test_registered_surface_classifier_rejects_feature_drift():
    rows = load_probe_rows(PROBE)
    classifier = fit_surface_classifier(rows)
    incomplete = dict(rows[0].features)
    incomplete.pop("diff_size")
    try:
        classifier.score(incomplete)
    except ValueError as exc:
        assert "missing=['diff_size']" in str(exc)
    else:
        raise AssertionError("missing registered feature must fail closed")
