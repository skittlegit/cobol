# Pull Request

## Task

- Task ID: <!-- e.g. D4 -->
- Record: `docs/tasks/<ID>.md`

## What this does

<!-- One or two sentences: what changed and why. -->

## Checks

- [ ] `pytest tests/ -q` and `ruff check .` pass.
- [ ] `STATUS.md` and the task record are updated in this PR.
- [ ] No duplicate versions of code, data, or results were added.
- [ ] If `schemas.py` changed, every consumer and its tests were updated.
- [ ] No gate in `eval/report.py` changed after looking at test results.
