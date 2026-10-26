# Sequence 704: reject non-finite maintenance daemon bounds

Maintenance scheduler and wake-daemon adoption validation now rejects NaN, either infinity, and numeric values too large to represent as finite floats for positive timeout/reentry bounds. These checks fail closed before adoption can start. The tested code-only tree is `d37bd189a9f73b015f949fb75bed6c221dff8697`, based on verified main `a64e4b32d8e36a66847b8e9b744f4652b9cb923c` / `6dbd470d86e17c1bded61b970b73abcf82ee9244`. Twelve focused regressions passed; targeted mypy, privilege lint, syntax compilation, and diff checks passed. Three unrelated existing wake-daemon tests failed locally and reproduced unchanged on the clean verified base; they are listed in the evidence record.

Evidence record: `work/construction/evidence/0704-reject-nonfinite-maintenance-daemon-bounds.json`
Evidence SHA-256: `08a6c9dffd9615b8fac23b2d0e0453799380d52ffbefcfe6059fe3f870562bbd`
