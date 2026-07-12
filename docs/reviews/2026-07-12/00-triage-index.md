# External review triage — 2026-07-12

Source: external agent review of 115 files + playbook, run **before** the T2.5
Phase-2 close and the track-a merge. Every finding below was re-verified against
the current tree. Buckets:

- **FIX-NOW** — safe, owned by us or trivial; do immediately → `fix-now.md`.
- **CHAT/contract** — touches frozen `schemas.py`/`CONTRACT.md`; decision only →
  `contract-change-track-c.md`.
- **CHAT/design** — a spec/design call for a track → `chat-track-a.md`.
- **FLAG→code** — real bug, no decision, route to owning track's branch →
  `flags-drafts.md`.
- **FLAG→defer** — real but not now; backlog → `flags-drafts.md` / below.
- **OBE** — overtaken by our recent work; no action.

## Categorization

| # | Finding | Verified | Bucket | Owner | Goes to |
|---|---------|----------|--------|-------|---------|
| F1a | "T1.4 unfinished" blocks T2.2 | STALE — T1.4 done (M1 PASSED) | **OBE** | A | — (T2.2 now blocks on T1.5 only) |
| F1b | No MO-4 / MO-3× / MO-6×; MO-1x is ASCII `x` (×2, not ×1) | yes | **FLAG→defer** (T2.2 prep) | B | below + T2.2 work order |
| F1c | `current_value` heterogeneous, no common comparator | yes | **CHAT/contract** (2nd item) | C | `contract-change-track-c.md` |
| F2 | Schema can't bind interprocedural line→program | yes | **CHAT/contract** | C | `contract-change-track-c.md` |
| F3 | GitHub automation undiscoverable (codeql dir/branch, ISSUE_TEMPLATE, no CI) | yes | **FIX-NOW** (moves) + 1 CI task | infra | `fix-now.md` |
| F4 | Stale provenance: 15 CC "secondary-mapped"; manifest KYC-provisional + gnucobol "implemented" | yes | **FIX-NOW** | B | `fix-now.md` |
| F5 | Qualified names not case-insensitive through trace API | yes | **FLAG→code** | A | `flags-drafts.md` |
| F6 | Preprocessor silently drops unterminated EXEC/COPY at EOF | yes | **FLAG→code** | A | `flags-drafts.md` |
| F7 | Dead-code `entry_points` treats forest-roots as reachable | yes (per spec) | **CHAT/design** | A | `chat-track-a.md` |
| F8 | Hybrid retrieval returns `score=0.0` | yes (`index.py:226`) | **FLAG→code** | C | `flags-drafts.md` |
| F9 | Built wheel lacks grammar/regulation data | yes | **FLAG→defer** | pkg | below |
| F10 | `fetch_corpora.sh` skips CardDemo without HEAD-pin check | yes | **FLAG→code** | A | `flags-drafts.md` |
| H1 | ruff: unused `pytest` import `test_clauses.py:15` | yes | **FIX-NOW** | B/C | `fix-now.md` |
| H2 | `ruff format --check`: 22 files | yes | **FLAG→defer** (sweep) | all | below |
| H3 | network tests not excluded by default | yes | **FIX-NOW** | C | `fix-now.md` |
| H4 | README points to removed `spike_parser.py`; "packaging not landed" | yes | **FIX-NOW** | docs | `fix-now.md` |
| H5 | `branching.md` main/master + track-branch conflict | yes | **FIX-NOW** | docs | `fix-now.md` |
| H6 | CODEOWNERS omits `tool_types.py`; `schemas.py` missing Track A | yes | **CHAT/design** (confirm owners) | C/all | `chat-track-a.md` note |
| H7 | `pin_regulations.py:18` "seven files" (roster is 8) | yes | **FIX-NOW** | B | `fix-now.md` |

## Deferred backlog (no single owner / not now)

**Moved to the canonical root `/BACKLOG.md`** (session-start protocol reads it
alongside STATUS/FLAGS): F1b → **BL-1** (MO coverage), F9 → **BL-2** (wheel
package-data), H2 → **BL-3** (format sweep), plus the deferred F3 CI workflow →
**BL-4**. Descriptions live there; this line is the pointer.

## Do NOT let an agent auto-patch

- `schemas.py`, `CONTRACT.md`, `tool_types.py` (SCHEMA FREEZE → F2, F1c, H6).
- Anything spanning >1 track's `src/` modules in a single commit (ownership).
