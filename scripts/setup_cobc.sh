#!/usr/bin/env bash
# T1.5: install the GnuCOBOL compile/behavior oracle (cobc) for run_cobol.py.
# Idempotent: skips the install if cobc is already on PATH.
set -euo pipefail

if command -v cobc >/dev/null 2>&1; then
    echo "cobc already present: $(command -v cobc)"
    cobc --version | head -1
    exit 0
fi

# Ubuntu base (validated in the T0.5 spike): cobc ships as gnucobol3.
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y gnucobol3
else
    echo "apt-get not found. Install GnuCOBOL for your platform, then ensure" >&2
    echo "'cobc' is on PATH (or set the COBC environment variable)." >&2
    echo "  macOS:   brew install gnu-cobol" >&2
    echo "  Windows: pacman -S mingw-w64-ucrt-x86_64-gnucobol  (msys2 ucrt64)" >&2
    exit 1
fi

echo "installed:"
cobc --version | head -1
