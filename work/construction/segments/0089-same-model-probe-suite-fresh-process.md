# 0089 — Recover same-model probe suites in a fresh interpreter

Source baseline: `4c7288f818b3588888df3bd2e9487276e104a896`, tree `0471d1fe98600698aeb08b97cbc2097578e6de0b`. Extended the same-model partial-suite integration case with a separate Python interpreter that opens the original developmental experiment store and calls its canonical `load_run` verifier. The child reconstructs the exact objective evaluation and the three per-condition correct counts `[2, 0, 2]`; it has no endpoint object and performs no inference.

Targeted fresh-process case: **1 passed, 0 failed, 0 skipped**. Python compilation and `git diff --check` passed. Evidence: `work/construction/evidence/0089-same-model-probe-suite-fresh-process-junit.xml` and `work/construction/evidence/0089-same-model-probe-suite-fresh-process-results.json`. This is deterministic fixture recovery, not real-model capability or production validation.

Next: verify seq88 hosted source checks when they complete; continue checking adjacent durable consumers for score identity/authority separation.
