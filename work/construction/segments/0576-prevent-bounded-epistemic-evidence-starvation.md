# Sequence 576 — prevent bounded epistemic evidence starvation

The retained-experience integration fix merged as PR #2614. Candidate `970105b9e7ac25286068d85287e7ff8da59940f4` was verified against main `7d55b9757a10322d680f6fb450691de7ff7f8506`, tree `5560f4b347e55fb5b2c9c68e2cb65cc4d93c729d`. It resolves durable evidence-binding identities before the per-tick cap, and applies state-update capacity only to pending changes, preserving deterministic ordering and explicit omission IDs.

The focused regression suite passed (25 tests), targeted Mypy reported zero issues, and compilation/diff checks passed. Hosted CI passed (143 passed, 13 skipped); exact-candidate Quality Gate completed strict Administrator audits and immutability, finalizer and separate metadata guard passed, and acceptance was 47/47. PR #2614 merged normally as `1b35e8a9b7e5eb91a93bf39fea4b6e34f572d0c4`, preserving the candidate tree and ordered parents. Post-merge checks passed; Forge Smoke was conditionally skipped.

No inference, goal execution, or production transition occurred.

Sequence: 576 (verified epistemic evidence-selection repair)
