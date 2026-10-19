# Active construction checkpoint

## Latest verified main

PR #2404 regular-merged sequence 437 at main `e66ac2f937db789380ae3da7f2999e4f2a5cd028`, preserving candidate tree `cf063909f5e4f16b22dae09b1ee7cd5a93f09fec`. Its exact-candidate Required Quality Gate #39217207658, CI #39217207619, Invariants #39217207678, Codex CI #39217207718, Docker #39217207597, Gradient #39217207664, Release #39217207626, and Lint Benchmark #39217207665 passed.

Sequence 437 recorded the post-merge main-push checks on the preceding SHA `8a3d72b9b608dbe41753f454d215b5528ef854dd`; those passed, including Required Quality Gate #39216241571 and CI #39216241670. Scheduled Federation Health and nightly runs on that SHA remain unobserved.

## Current construction

Sequence 438 adds explicit noninteractive Administrator preflights to both nightly workflows and prevents `audit-nightly` from starting its write-enabled repair job unless the read-only audit job succeeded. Strict audit requirements and existing narrow permissions remain intact. Hosted checks are pending.

## Open evidence boundaries

- Historical test provenance remains `INTEGRITY_BROKEN` at its unanchored start; the preserved sequence-286 loss remains unresolved.
- A production resident A→B→A trial still requires commissioned identities, distinct serving approvals, and operator preregistration.
- No production resource-observer execution, longitudinal learning, or benefit is claimed.
- Sequences 382–386 and stale sequence-178, sequence-411, and sequence-417 workspaces remain untouched.
- No production authority or workflow privilege changed.

Latest verified main: `e66ac2f937db789380ae3da7f2999e4f2a5cd028`, tree `cf063909f5e4f16b22dae09b1ee7cd5a93f09fec`.
Latest construction segment: `work/construction/segments/0438-gate-nightly-repairs-on-admin-preflight.md`
Latest segment SHA-256: `2c5752216dfcfbe631ada9e3a6efd3535bd1e7e2bc733f503d01ae8272ead4f1`
Sequence: 438 (workflow source candidate; hosted verification pending)
