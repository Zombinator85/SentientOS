# Active construction checkpoint

## Latest verified main

PR #2425 regular-merged sequence 458 as main `f37d758e26421b91939930b6fd9ffacc2e110a4b`, preserving tree `d48c0ee2663b3d21d5d00f2723698cf207b05935`. Its exact-head matrix and main post-merge Required Quality Gate, CI, invariants, CPU Docker smoke, Docker build, and Docs Deploy passed. Forge Smoke was skipped by condition. Sequence 458 records sequence 457's integration and the scheduled-run boundary.

Historical scheduled failures confirmed the former nightly audit workflows lacked Administrator execution. Both current main workflow definitions now put Administrator preflight before strict audit. Self Check is read-only and runs privilege lint, Mypy, pytest airlock, and pytest. Audit Integrity keeps the audit job read-only and grants contents/PR write only to its Administrator-gated safe-repair job, followed by strict verification. Nightly Self Check #39235681245 passed on `b5912ecc...`; Nightly Audit Integrity #39228761152 passed on `fd20cf6...` with repair skipped.

## Open evidence boundaries

- At 2026-10-19 11:35:57 UTC, no scheduled Federation Health run on current main `f37d758e...` was present. The latest scheduled run is #39218331969 on older main `e66ac2f...`; successful push run #39235242309 is not scheduled evidence.
- The Audit Integrity repair publication path was not exercised by its recent scheduled success. Repository policy blocks Actions-token PR creation, which the repair workflow uses after safe repair. Its current write permissions are limited to the repair job; no authority was broadened.
- Historical test provenance remains `INTEGRITY_BROKEN`; the sequence-286 loss is preserved.
- A production resident A→B→A trial requires commissioned identities, distinct serving approvals, and operator preregistration. No production resource-observer execution, longitudinal learning, or benefit is claimed.
- Sequences 382–386 and stale sequence-178, sequence-411, and sequence-417 workspaces remain untouched.

Latest verified main: `f37d758e26421b91939930b6fd9ffacc2e110a4b`, tree `d48c0ee2663b3d21d5d00f2723698cf207b05935`.
Latest construction segment: `work/construction/segments/0459-confirm-nightly-privilege-repair-history.md`
Latest segment SHA-256: `46f1988c9fe0dc7676d71851112971f2cd74db51d32bf14862f4c74b65c2fd12`
Sequence: 459 (nightly privilege repairs verified; Health schedule and repair publication pending)
