# Sequence 512 — reject non-finite transition context values

Python's JSON encoder accepts NaN and infinities by default even though they are not valid JSON numbers. The recursive freeze boundary now permits only finite floats, preserving strict JSON compatibility for directly constructed transition-stage approval contexts. Regressions reject NaN, positive infinity, and negative infinity and are included in hosted transition receipt validation.

Sequence 511 is verified and merged as PR #2519, main commit `dd51df9fc0aa21f8ecac732df590716f14d801bb`, tree `2ff89a56f9c8881f7ba66237baf22c5755d6b390`. Its exact-candidate Required Quality Gate passed actual Administrator strict audits, hosted finalization, and the separate pre-publication metadata guard. CI, Docker, Release validation, Codex CI, invariants, lint matrix, and Gradient regression passed. Post-merge workflow runs were not independently observable through the available connector.

Supplemental local verification passed 92 affected tests with 0 failures and 0 skips. Targeted Mypy, compileall, workflow YAML parsing, diff checks, and custody across 511 predecessors passed. Exact-candidate hosted checks for sequence 512 are pending. No production transition, activation, serving, inference, or writeback was performed.

Verified main base: `dd51df9fc0aa21f8ecac732df590716f14d801bb`, tree `2ff89a56f9c8881f7ba66237baf22c5755d6b390`
Implementation candidate: `ddfeba77456cd003cf8b3ff1f0a80ff9413c256d`, tree `ef6b99202f9924a0ccd5843b8273b79cade05478`
Sequence: 512 (candidate pending hosted verification)
