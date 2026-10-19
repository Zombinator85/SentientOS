# Active construction checkpoint

## Latest verified main

PR #2394 regular-merged the exact sequence 426 candidate as main `624e4ee32bb6dca9b45053571034613bb2bdbb0d`, preserving candidate tree `3e6457e82145275aeba048ce5a85093726704f7b`. PR #2393 previously regular-merged sequence 424 at `5611dbddc6b4cc55116692833b1b201cd4c149c2`, preserving candidate tree `38124ee137974910354e1a1f9e38a9a68db6368e`.

The exact sequence 426 PR checks passed: CI #39207131067, Required Quality Gate #39207131155, Docker #39207131034, Invariant Tests #39207131058, Codex CI #39207131118, Lint Benchmark #39207131289, Gradient null regression #39207131089, and Release validation #39207131187. Its exact main push checks passed on `624e4ee32bb6dca9b45053571034613bb2bdbb0d`: CI #39207492221, Required Quality Gate #39207492167, Docker #39207492289, Invariant Tests #39207492158, Codex CI #39207492177, and Docs Deploy #39207492050. Forge Smoke #39207492170 skipped by condition.

## Verified hosted workflow executions

After sequence 424 merged, Federation Health run #39207087017 succeeded on main `5611dbddc6b4cc55116692833b1b201cd4c149c2`. The Administrator UID preflight and `sudo -n` updater passed; artifact #12166157341 (223 bytes, SHA-256 `8145c1e0b2d09128c71315b44aca8c109f6f57fe94b7f417efd38a3f16f0fe8b`) was uploaded. Scheduled run #39184847466 also passed on main `944269a771c6f6300d6f8a559866ade9e262a56b` with its Administrator preflight and report artifact.

Nightly Audit Integrity #39207086986 and Nightly Self Check #39207086970 both succeeded on main `5611dbddc6b4cc55116692833b1b201cd4c149c2`. The audit repair job was skipped after strict verification succeeded. Self Check completed mypy baseline ratchet, pytest airlock, and 143 passed / 13 skipped tests; provenance and trend artifacts were uploaded. The audit log also reported one optional, non-blocking support-log previous-hash mismatch. It remains unmodified and is preserved as an open observation.

## Current work

Sequence 427 records these post-merge results and merge lineages. It is an evidence-only candidate based on verified main `624e4ee32bb6dca9b45053571034613bb2bdbb0d` / tree `3e6457e82145275aeba048ce5a85093726704f7b`. The next hourly Federation Health schedule is expected at 06:17 UTC and remains pending for this evidence cut.

## Open evidence boundaries

- Historical test provenance remains `INTEGRITY_BROKEN` at its unanchored start; the preserved sequence-286 loss remains unresolved.
- No production resident A→B→A trial or production inference occurred. Commissioned identities, distinct serving approvals, and operator preregistration remain required.
- Sequences 382–386 and all prior indexed records remain preserved. Stale sequence-178, sequence-411, and sequence-417 workspaces remain untouched.
- No production authority or workflow privilege changed.

Latest verified main: `624e4ee32bb6dca9b45053571034613bb2bdbb0d`, tree `3e6457e82145275aeba048ce5a85093726704f7b`.
Latest construction segment: `work/construction/segments/0427-record-main-workflow-execution-evidence.md`
Latest segment SHA-256: `c3aa52217effea8ea967df5db21f12f4802a80159b5f581bbeeb1d758a51e90b`
Sequence: 427 (evidence candidate; hosted validation pending)
