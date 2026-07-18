# Security Policy

## Status and scope

COBOL Archaeologist is a **pre-release research project and benchmark**. There
are no tagged releases yet; security fixes land on the default branch. This
policy will be revised when the benchmark and system are versioned
(`benchmark/v1`, T5.2) and when the self-hostable MCP server ships (T7.1/T7.2).

The benchmark corpora are public code — AWS CardDemo (Apache 2.0) and IBM CICS
CBSA (EPL 2.0). The **security-sensitive surface is the running system**,
especially when self-hosted against a bank's own proprietary COBOL: the COBOL
execution harness, the MCP tool server, and the agent's handling of ingested
source and regulation text.

## Reporting a vulnerability

**Do not open a public issue for security reports.** Public issues are for
non-sensitive bugs only.

Report privately through GitHub's **private vulnerability reporting**, which is
enabled for this repository: use the "Report a vulnerability" button under the
repository's **Security** tab, or open the
[private report form](https://github.com/skittlegit/cobol/security/advisories/new).

Please include: affected component (e.g. `run_cobol`, MCP server, `rag/`, agent
loop), version or commit hash, a description of the impact, and reproduction
steps or a proof of concept. If the report involves untrusted input (a crafted
COBOL program, copybook, or regulation document that triggers the issue), attach
the minimal triggering artifact.

## Response expectations

This is a research project maintained on a best-effort basis, not a commercial
product with a formal SLA. That said, we aim to: acknowledge a report within **5
business days**, confirm or dispute it within **15 business days**, and
coordinate a fix and disclosure timeline with you from there. We support
coordinated disclosure and will credit reporters who want it.

## Security model — what to know before you deploy

### `run_cobol` executes untrusted code

The compile/execute harness (`model/run_cobol.py`, T1.5) invokes GnuCOBOL `cobc`
on COBOL slices and runs the resulting binaries. **All input to it must be
treated as untrusted and hostile.** It is a deliberate arbitrary-code-execution
surface. Required operator posture: run it only inside an isolated sandbox
(container or jail) with CPU/memory/wall-clock limits, no outbound network, and
a read-only or ephemeral filesystem. Do not point it at untrusted programs
outside such containment. The sandbox-and-timeout requirement is part of T1.5's
acceptance criteria; treat any deployment where those are absent as unsafe.

### Self-hosting and proprietary code

The system is designed to be **self-hostable / on-prem** precisely so
proprietary bank code and internal regulation documents never leave the
operator's environment. When ingesting non-public code, run fully on-prem with
the offline embedder and a local model backend (Ollama/GGUF path, T7.2); do not
route proprietary source or regulation text to an external LLM API without an
explicit data-processing agreement. The MCP server exposes the tool layer —
deploy it on a trusted network only, authenticate clients, and do not expose it
to the public internet.

### LLM / agent-specific risks

The agent (T3.5) feeds **ingested COBOL source and retrieved regulation text
into an LLM** in a tool-calling loop. Treat ingested content as a
prompt-injection vector: a crafted comment, identifier, or regulation passage
may attempt to steer the agent or its tool calls. Mitigations in the design
reduce, but do not eliminate, the risk:

- tools return structured data plus pointers rather than raw dumps;
- verification is tiered with an independent-model-family entailment check
  (T3.4);
- findings carry an auditable trace.

Do not wire agent output to side-effecting actions without a human in the loop.

### Supply chain

`tree-sitter-cobol` is **vendored and commit-pinned**; GnuCOBOL is used only as
a compile oracle. Codebase and dependency pins live in `data/manifest.json`.
Report any pin that resolves to unexpected content.

## Out of scope

- **Findings are advisory, not legal or compliance advice.** The system flags
  _possible_ regulatory drift for human review; it is not a source of truth for
  a bank's regulatory obligations and must not be the sole basis for a
  compliance decision. This is a correctness limitation, not a vulnerability.
- The public benchmark data (CardDemo/CBSA-derived instances) is intentionally
  public; issues in it are data-quality bugs, filed via the normal issue
  template, not security reports.
- Vulnerabilities in third-party dependencies should be reported upstream; tell
  us so we can bump the pin.
