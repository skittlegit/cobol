#!/usr/bin/env bash
# Run eval.runner inside WSL until every requested row has a current result,
# waiting out Codex usage limits. Rows already done are skipped on each retry,
# so restarting never repeats work.
#
#   bash scripts/run_until_done.sh detector --split dev --workers 6
#
# Only a stop caused by Codex accounts (CodexAuthError: every logged-in account
# is out of its usage window or logged out) is retried, after
# COBOL_ARCH_LIMIT_WAIT seconds (default 30 minutes). Any other failure exits.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WAIT="${COBOL_ARCH_LIMIT_WAIT:-1800}"
LOG="$(mktemp)"
trap 'rm -f "${LOG}"' EXIT

for attempt in $(seq 1 48); do
    if bash "${REPO}/scripts/wsl_run.sh" cobol_archaeologist.eval.runner "$@" 2>&1 | tee "${LOG}"; then
        exit 0
    fi
    if ! grep -q "CodexAuthError" "${LOG}"; then
        echo "runner failed for a reason other than Codex limits; not retrying" >&2
        exit 1
    fi
    echo "$(date -Is) all Codex accounts unavailable (attempt ${attempt}); retrying in ${WAIT}s"
    sleep "${WAIT}"
done
exit 1
