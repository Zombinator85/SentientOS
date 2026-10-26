# Sequence 712: reject non-finite commissioning bounds

Initial POSIX resident commissioning now rejects NaN, either infinity, and integers too large to convert to finite floats across all six positive count/time bounds. The tested code-only tree is `b2de30f0ad79f960888408dc4283ccbd0c4be3e5`, based on verified main `44668bd35693c776c467e862c6c3d799df682b5c` / `00b1f381bd4735e5ddf2ab42c2b2f1968bfd4fbc`. All 30 focused regressions and all 50 tests in the affected module passed; targeted mypy, read-only privilege lint, syntax compilation, and diff checks passed.

Evidence record: `work/construction/evidence/0712-reject-nonfinite-commissioning-bounds.json`
Evidence SHA-256: `5634b2a7032c6a2cfb254d7264502db4f1b42f5f1331536b528a76f8fb8f1959`
