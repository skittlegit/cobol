# Linux container preparation and qualification

The Linux profile is additive to the sealed Windows standalone payload. Its
Python version, dependency wheels, CPU torch identity, toolchain and manifest
are recorded separately. Windows native wheels are never reused as Linux
dependencies. The unchanged pure-Python project wheel carries the same source
and pinned grammar/regulation assets.
Applicable dependency versions remain locked to the standalone stack, with an
explicit CPU torch variant; platform-inapplicable Windows dependencies are not
installed. Each native Linux wheel receives its own checksum.

The preparation phase may use the network inside disposable Docker build/run
containers to stage official Debian toolchain packages, Python dependency
wheels, and CPU torch from `https://download.pytorch.org/whl/cpu`. It does not
install host software. Resolve the Python 3.12 base to an immutable repository
digest before building `Dockerfile.preparer`, and bind the final preparer image
digest in the Linux qualification receipt.

Run `linux_payload.py` inside the preparation container with a read-only `/input`
mount containing the project wheel, unchanged `offline.py`, regulation assets
and prior manifest; read-only `/models` containing the exact existing verified
model snapshots; and a new writable `/out` staging directory. That helper
creates a distinct Linux wheelhouse, records every wheel version/checksum,
creates exact hash-locked offline requirements and verifies all local payloads.
Model bytes are copied from the approved cache; no model download occurs.

Build the unchanged deployment Dockerfile against the completed Linux bundle
and pinned toolchain base with `docker build --network=none`. The image installs
into a clean virtual environment exclusively from the local verified wheelhouse.
Its runtime uses UID/GID 65532, stdio, a read-only root filesystem, writable
temporary filesystem with `exec` enabled for the local grammar shared library
and GnuCOBOL batch binaries, read-only external corpus/COPY mounts and
`--network=none`. It carries only declared model/runtime payloads, not generic
user caches, credentials, provider logs or benchmark gold.

Use `container_smoke.py --image IMMUTABLE_IMAGE_ID --corpus FIXTURE_DIRECTORY`
from an MCP client environment. It invokes the real Linux parser, slice and
hybrid/rerank regulation search and checks that CICS execution is explicitly
unavailable. Exactly eleven tools must be listed. Actual runtime configuration,
subprocess exit codes, manifests and stdout/stderr are retained under
`deploy/qualification/`; a previous blocked preparation record remains
historical evidence and is not rewritten when later qualification succeeds.
