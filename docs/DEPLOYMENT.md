# Offline stdio deployment

This deployment wrapper uses the unchanged eleven-tool MCP adapter and actual
parser, graph, slicing, compiler and regulation retrieval implementations.
The default retrieval profile is `hybrid_rerank`; `bm25` is an explicit lexical
profile. No cloud provider key is required. Stdio is the only supplied transport.

Prepare on a connected staging workstation of the same operating system,
architecture and Python 3.12 ABI as the target. The builder consumes existing
pip wheel cache entries and exact local model snapshots; it never downloads.
Missing dependencies or model snapshots stop preparation with an error.

```powershell
python deploy/build_bundle.py --output C:/staging/bundle
python deploy/offline.py verify --bundle C:/staging/bundle
python deploy/offline.py install --bundle C:/staging/bundle --environment C:/offline/runtime
C:/offline/runtime/Scripts/python.exe C:/staging/bundle/offline.py serve --bundle C:/staging/bundle --corpus C:/corpora --copybook C:/copybooks
```

On Linux use `/offline/runtime/bin/python`. Transfer the complete bundle and
manifest together through your approved process. Verify the manifest against a
trusted externally recorded digest before installation. Checksums establish
integrity against that manifest, not publisher authentication. Installation uses
`--no-index`, binary wheels and exact `--require-hashes` dependency pins into a
new virtual environment, without system or editable project packages.

The manifest records the Python executable hash/version/platform, wheel hashes
and versions, grammar revision, regulation payload hashes, and embedder,
reranker and NLI snapshot commits. The historical NLI source uses the `main`
alias; deployment resolves it to exactly one immutable cached snapshot and
records that alias and commit. Model bytes are copied into the verified payload.
Generic caches, corpora, provider logs, benchmark labels and credentials are not
included. Windows wheels cannot be used by a Linux container: stage each target
platform separately.

Mount your licensed corpus and COPY paths read-only. A missing corpus, missing
COPY directory, required payload, model weights or any checksum mismatch stops
startup. Required model snapshots must be cached even when choosing BM25; that
profile changes retrieval, not the verified bundle's declared payload.
The wrapper explicitly supplies bundled regulation chunks and clauses rather
than relying on checkout-relative fixture paths.

Hub access and telemetry are disabled. A Python audit hook rejects socket
external connections, DNS lookups and listener binds. Loopback is allowed for
Windows asyncio's private socketpair. This is an application-level guard;
use the host firewall or a network-isolated container to enforce air-gap policy
against native code and subprocesses. No OS-level network isolation is implied
by a Python smoke alone. Stdio keeps protocol output on stdout; diagnostics go
to stderr. Store logs according to your corpus confidentiality requirements.

GnuCOBOL is an optional operator-supplied external dependency, version of record
3.2.0, supported range `>=3.1.2,<4`. A missing compiler is an explicit tool error;
CICS that the supported compiler cannot execute returns Tier-1 unavailable.
Neither result establishes executed compliance. Supply a local C compiler for
the pinned tree-sitter grammar's first build; the vendored grammar requires no
network download. Python and compiler binaries are external payloads, not
silently represented as bundled files.

Run the actual client using the clean environment interpreter:

```powershell
C:/offline/runtime/Scripts/python.exe deploy/smoke.py --bundle C:/staging/bundle --corpus tests/fixtures/hunts/corpus
```

It lists exactly eleven tools and calls `read_program`, `slice_on`,
`search_regulations`, and the CICS execution-unavailable path over stdio.
The deployed executable `cobol-archaeologist-mcp` remains the unchanged adapter;
launch through the verified wrapper to enforce payload and offline gates.

For containers, place only the bundle under `deploy/bundle/`, use an already
staged base image pinned by digest containing Python 3.12 and a C compiler,
then build with networking disabled:

```sh
docker build --network=none --build-arg BASE_IMAGE=local-python@sha256:YOUR_DIGEST -f deploy/Dockerfile deploy
docker run --rm -i --network=none --read-only --tmpfs /tmp --mount type=bind,src=/licensed/corpus,dst=/corpus,readonly --mount type=bind,src=/licensed/copybooks,dst=/copybooks,readonly IMAGE
```

The image runs as UID/GID 65532 and performs no package/model downloads. Runtime
corpora are mounts, never image layers. No HTTP profile, remote authentication,
TLS or multi-tenant isolation is supplied; such deployment requires separate
design and security testing.

For upgrades, create a fresh verified bundle and environment, rerun the stdio
smoke, and switch the launcher only after checks pass. Keep the old manifest
and qualification receipt for rollback. Remove an obsolete environment and
bundle only after verifying their resolved paths and that no launcher uses
them. Never remove mounted corpus data as part of package removal.
