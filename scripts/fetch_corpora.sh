#!/usr/bin/env bash
# T1.0: fetch benchmark corpora into data/corpora/ (never vendored into the repo).
# Idempotent: skips a corpus whose checkout already exists.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORPORA="$ROOT/data/corpora"

# Full SHA from data/manifest.json (canonical); short form 59cc6c2fd7eb.
CARDDEMO_PIN="59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
CARDDEMO_URL="https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git"
CBSA_URL="https://github.com/cicsdev/cics-banking-sample-application-cbsa.git"

mkdir -p "$CORPORA"

# DECISION: checkout directory names "carddemo" and "cbsa" (work order leaves
# them unspecified); tests/test_scaffold.py depends on "carddemo".
if [ -e "$CORPORA/carddemo" ]; then
    echo "carddemo already present, skipping"
else
    git init -q "$CORPORA/carddemo"
    git -C "$CORPORA/carddemo" remote add origin "$CARDDEMO_URL"
    git -C "$CORPORA/carddemo" fetch --depth 1 origin "$CARDDEMO_PIN"
    git -C "$CORPORA/carddemo" checkout -q FETCH_HEAD
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
