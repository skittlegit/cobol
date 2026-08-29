# Evaluation artifacts

`STATUS.md` at the repository root is the unversioned canonical dashboard.
The active configuration-4 M4 evaluation continues from the existing 22/102
checkpoint in the plain `m4/lineage/` tree.

The 102 signed requests retain their original frozen tool-command text. A
fail-closed host compatibility mapping resolves that one historical staging
path to `m4/lineage/train-dev/adaptive_agent/task-staging`; no duplicate old
directory exists. The completed configuration-3 predecessor and earlier
required runs stay under `legacy/`.

Superseded run trees and lineages belong under `legacy/`. Version tokens that
are part of a data contract (for example schema identifiers, attempt numbers,
or values embedded in sealed manifests) remain in the artifact content because
they identify protocol records rather than competing current files.
