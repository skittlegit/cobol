#!/usr/bin/env bash
# T1.0: fetch benchmark corpora into data/corpora/ (never vendored into the repo).
#
# Idempotent, and PIN-VERIFYING: an existing carddemo checkout is only accepted
# if its HEAD equals CARDDEMO_PIN. A stale checkout silently invalidates every
# line-level fixture and benchmark label in the repo (labels are line-numbered
# against this exact commit), so a mismatch is a hard failure with remediation
# instructions rather than a silent skip (review 2026-07-12, F10).
#
# Manual check (what this script automates):
#   git -C data/corpora/carddemo rev-parse HEAD    # must equal CARDDEMO_PIN
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORPORA="$ROOT/data/corpora"

# Full SHA from data/manifest.json (canonical); short form 59cc6c2fd7eb.
CARDDEMO_PIN="59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
CARDDEMO_URL="https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git"
CBSA_URL="https://github.com/cicsdev/cics-banking-sample-application-cbsa.git"

mkdir -p "$CORPORA"

fetch_carddemo() {
    git init -q "$CORPORA/carddemo"
    git -C "$CORPORA/carddemo" remote add origin "$CARDDEMO_URL" 2>/dev/null \
        || git -C "$CORPORA/carddemo" remote set-url origin "$CARDDEMO_URL"
    git -C "$CORPORA/carddemo" fetch --depth 1 origin "$CARDDEMO_PIN"
    git -C "$CORPORA/carddemo" checkout -q FETCH_HEAD
}

# DECISION: checkout directory names "carddemo" and "cbsa" (work order leaves
# them unspecified); tests/test_scaffold.py depends on "carddemo".
if [ -e "$CORPORA/carddemo" ]; then
    HEAD_SHA="$(git -C "$CORPORA/carddemo" rev-parse HEAD 2>/dev/null || echo "")"
    if [ "$HEAD_SHA" = "$CARDDEMO_PIN" ]; then
        echo "carddemo already at pin ${CARDDEMO_PIN:0:12}, skipping"
    else
        # DECISION: fail loudly rather than auto-`rm -rf` the checkout. The dir
        # may hold local work, and this script must never destroy something the
        # operator did not ask it to; re-cloning is one explicit command away.
        echo "ERROR: data/corpora/carddemo is NOT at the pinned commit." >&2
        echo "  expected: $CARDDEMO_PIN" >&2
        echo "  found:    ${HEAD_SHA:-<not a git checkout>}" >&2
        echo "" >&2
        echo "Line-level fixtures and benchmark labels are pinned to this commit." >&2
        echo "Re-fetch with:" >&2
        echo "  rm -rf data/corpora/carddemo && bash scripts/fetch_corpora.sh" >&2
        exit 1
    fi
else
    fetch_carddemo
fi

if [ -e "$CORPORA/cbsa" ]; then
    echo "cbsa already present, skipping"
else
    git clone --depth 1 "$CBSA_URL" "$CORPORA/cbsa"
fi

# CBSA has no upstream pin yet (data/manifest.json: pin when first used);
# record the commit actually fetched.
{
    echo "carddemo $(git -C "$CORPORA/carddemo" rev-parse HEAD)"
    echo "cbsa $(git -C "$CORPORA/cbsa" rev-parse HEAD)"
} > "$CORPORA/PINNED"

echo "corpora ready under $CORPORA"
cat "$CORPORA/PINNED"
