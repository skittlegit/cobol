# T6-v2 blinded review packet

`packet.jsonl` is a **coordinator-only release queue**, not a distributable
full packet. Each record contains one authority/code judgment, an opaque
side-specific source alias, and the source text needed for reviewer-led
localization. It omits pair IDs, temporal-side markers, canonical source paths
and hashes, proposer-selected code loci, proposed labels, and rationales.

The coordinator must follow `release-policy.json`: release exactly one item at
a time, do not provide the complete queue, do not provide `../candidates/` or a
canonical source map, and start the independent pass without the AI-primary
responses or model context. A response-metadata artifact must attest
these controls. Because identical code cannot be made cryptographically
unlinkable in a reusable offline bundle, pair unlinkability depends on this
sequential delivery and context-isolation protocol.

The earlier Luna/max pass used a superseded packet that disclosed canonical
paths, hashes, and proposer-selected loci. It is retained under `../diagnostics/`
as a compromised diagnostic only and is ineligible as independent verification.

For each record, replace the null fields inside `review_response` with:

- `decision`: `include`, `exclude`, or `needs_adjudication`;
- `drift_type`: one D1-D7 label, or null when excluded;
- `line_level`: an array of reviewer-localized
  `{program, line, source_alias}` citations from the visible source text;
- `rationale`: a source-grounded explanation; and
- `uncertainty_notes`: a string or null.

Return responses as a separate JSONL artifact. Do not edit this frozen packet.
The preparation manifest remains non-evaluable until both passes and any
adjudication are recorded and a new freeze is produced.

## Coordinator handoff commands

Run these commands from the repository root. The workspace should be handed to
the reviewer without repository access; it contains at most `current-item.json`.
The amended primary pass is explicitly AI-primary, not human review. Its
frozen `ai-primary-policy.json` requires a fresh, isolated
`gpt-5.6-sol`/`max` context for every attempt and prohibits any artifact or
report from representing this pass as human review.

```powershell
.venv\Scripts\python.exe scripts/t6_review_coordinator.py init `
  --workspace .tmp/t6-ai-primary `
  --reviewer "model_ai_primary;model=gpt-5.6-sol;reasoning=max;fresh-pass=v1" `
  --role ai_primary
.venv\Scripts\python.exe scripts/t6_review_coordinator.py release `
  --workspace .tmp/t6-ai-primary
```

The reviewer reads only `current-item.json` and returns one JSON response that
matches `response.schema.json`. Record it, then release the next item:

```powershell
.venv\Scripts\python.exe scripts/run_t6_independent_review.py `
  --workspace .tmp/t6-ai-primary `
  --audit-dir .tmp/t6-ai-primary-private-audit `
  --review-role ai_primary `
  --transport native --codex-binary path/to/codex.exe `
  --chatgpt-account-sha256 FROZEN_ACCOUNT_SHA256
```

After all 22 responses, freeze the pass metadata:

```powershell
.venv\Scripts\python.exe scripts/t6_review_coordinator.py finalize `
  --workspace .tmp/t6-ai-primary `
  --metadata .tmp/t6-ai-primary.metadata.json `
  --controlled-model-audit `
    .tmp/t6-ai-primary-private-audit/ai-primary-audit-manifest.json
```

Finalization pins both the hash-chained sequential delivery audit and the
controlled Sol/max request/raw-bundle audit. Missing, mismatched, non-Sol,
context-reusing, tool-using, or human-labeled primary evidence fails closed.

## Fresh Luna/max independent pass

Create a separate independent-verifier workspace. Its pseudonym must identify
the frozen model role; it must not reuse the human-primary workspace.

```powershell
.venv\Scripts\python.exe scripts/t6_review_coordinator.py init `
  --workspace .tmp/t6-luna-independent `
  --reviewer "model_independent_verifier;model=gpt-5.6-luna;reasoning=max;fresh-pass=v2" `
  --role independent_verifier
```

The private audit directory must be outside that reviewer workspace. A dry run
releases only the next envelope and freezes its request identity without making
a provider call:

```powershell
.venv\Scripts\python.exe scripts/run_t6_independent_review.py `
  --workspace .tmp/t6-luna-independent `
  --audit-dir .tmp/t6-luna-independent-private-audit `
  --transport native --codex-binary path/to/codex.exe `
  --chatgpt-account-sha256 FROZEN_ACCOUNT_SHA256 --dry-run
```

Remove `--dry-run` to execute. Every item uses a new ephemeral
`gpt-5.6-luna`/`max` Codex task with an empty source mapping and no authorized
tools. The host validates the strict response schema, attaches reviewer/time,
records the response through the coordinator, and deletes the active envelope.
Raw Codex events and request identities remain immutable in the private audit
directory and are never included in a later model prompt. The runner resumes a
completed raw bundle without a second provider call and uses a fresh isolated
attempt after schema-invalid output. It rechecks the frozen ChatGPT account
immediately before every provider call.

After all 22 items, the runner freezes
`independent-verifier-audit-manifest.json`. It reconciles ordinal order and
every retry's request identity, raw execution, completion marker, model,
reasoning effort, account hash, and isolation controls. Pin it when finalizing
the verifier metadata:

```powershell
.venv\Scripts\python.exe scripts/t6_review_coordinator.py finalize `
  --workspace .tmp/t6-luna-independent `
  --metadata .tmp/t6-luna-independent.metadata.json `
  --controlled-model-audit `
    .tmp/t6-luna-independent-private-audit/independent-verifier-audit-manifest.json
```

Promotion rejects verifier metadata without this aggregate. The superseded
Luna diagnostic is not an input to this runner and remains ineligible review
evidence.
