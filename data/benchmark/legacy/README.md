# Legacy benchmark inputs

This directory retains pre-freeze inputs that are still required to reproduce
and test the released benchmark. They are not active evaluation splits.

`v1-pre/` is retained because the freeze and regression tests use it to prove
how the active `v1/` benchmark was produced. The active `v1/` and `t6-v2/`
paths remain in place until R1/R2 finish because sealed requests and manifests
hash-bind their exact paths.
