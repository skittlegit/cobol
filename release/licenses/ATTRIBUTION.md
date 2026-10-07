# Release attribution

Project code, annotation guidelines and mutation operators are governed by the
repository MIT license in `LICENSE`.

The frozen v1 benchmark contains synthetic mutations and examples derived from
AWS CardDemo, licensed under Apache License 2.0. Its source repository is
https://github.com/aws-samples/aws-mainframe-modernization-carddemo, pinned at
`59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`. Project mutation operators modify
CardDemo-derived examples to introduce the drift cases described by each row's
provenance and gold rationale. These examples are research benchmark derivatives,
not an unmodified distribution of CardDemo. This attribution derives from
`data/manifest.json` and the licensing/composition sections of `DATASHEET.md`.
The upstream copyright notice is retained byte-for-byte as
`release/licenses/CardDemo-NOTICE.txt`, from the `NOTICE` file at that pinned
commit. The full Apache license is included as `release/licenses/Apache-2.0.txt`, copied
without modification from https://www.apache.org/licenses/LICENSE-2.0.txt.

Quoted RBI regulation text retains its original source rights. It is included
for research and citation purposes; the repository MIT license does not grant
rights to the underlying regulations. Refer to `data/regulations/sources/MANIFEST.json`
and the original RBI publications for authoritative text. RBI PDFs are excluded.

The secondary IBM CICS Bank Sample Application corpus is not consumed by the
frozen v1 benchmark and is excluded from this release. Fetched corpora, model
weights and provider capture logs are also excluded.
