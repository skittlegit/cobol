#!/usr/bin/env bash
# Run a cobol_archaeologist module inside WSL, where Codex, GnuCOBOL 3.2.0,
# and the models live. The repository on the Windows side is used in place.
#
#   wsl -d Ubuntu -- bash scripts/wsl_run.sh cobol_archaeologist.eval.runner detector --split dev
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${HOME}/.cache/cobol-archaeologist/host-venv"
UV="${HOME}/.local/bin/uv"
STAMP="${VENV}/.installed-from"

if [ ! -x "${VENV}/bin/python" ]; then
    "${UV}" venv --python 3.12 --seed "${VENV}"
fi
WANT="$(sha256sum "${REPO}/pyproject.toml" | cut -d' ' -f1)"
if [ "$(cat "${STAMP}" 2>/dev/null || true)" != "${WANT}" ]; then
    "${UV}" pip install --python "${VENV}/bin/python" \
        --index-url https://download.pytorch.org/whl/cpu torch
    "${UV}" pip install --python "${VENV}/bin/python" -e "${REPO}[dev,models]" transformers
    echo "${WANT}" > "${STAMP}"
fi

cd "${REPO}"
exec "${VENV}/bin/python" -m "$@"
