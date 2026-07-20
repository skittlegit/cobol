# BACKLOG — deferred technical debt & future work

Verified work that is deliberately unscheduled or postponed. This is separate
from the authoritative task ledger in `STATUS.md` and the cross-track inboxes
in `FLAGS.md`.

An item leaves this file when it becomes a canonical work order or when the
change that resolves it is committed. Resolved history remains available in
Git and the affected work orders; it is not duplicated here.

Session-start protocol: skim this alongside `STATUS.md` and `FLAGS.md`.

Format: **ID** — title · source · owner · trigger.

## Open

### BL-3 — Repository-wide Ruff format sweep

**Source:** review H2 · **Owner:** all tracks · **Trigger:** a coordinated quiet
window

`ruff format --check` flags about 22 files. A single sweep would touch modules
owned by every track. Land one sanctioned repository-wide commit or let each
track format only its own files to avoid ownership churn. `ruff check` is clean.

### BL-9 — Reconcile the locked GnuCOBOL version

**Source:** audit M4 · **Owner:** infrastructure · **Trigger:** a team decision

`CLAUDE.md` locks GnuCOBOL 3.1.2, while T1.5/T2.2 evidence records validation
on 3.2.0 and `scripts/setup_cobc.sh` installs the distribution's `gnucobol3`.
Choose one version of record and enforce it by pinning the setup script or
ratifying a change to the locked decision.

### BL-11 — Install repository review rulesets

**Source:** audit M6 · **Owner:** infrastructure · **Trigger:** before
`benchmark/v1` (T5.2) or the MCP release (T7.1)

The rulesets checked into `.github/rulesets/` have not been installed in the
live repository. Installing them changes collaborator push and merge behavior
and requires an explicit repository-administration action. Private
vulnerability reporting is enabled in `.github/SECURITY.md`; CODEOWNERS already
covers `tool_types.py` and requires all three tracks for the frozen schema.
