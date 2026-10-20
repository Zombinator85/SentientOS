# Sequence 488 — verify persisted priority admission readback

## Regression increment

PR #2478 extends the sequence 487 integrated daemon-planning regression to reopen the persisted canonical work plan and then load its immutable evidence binding through the production readback path. The test asserts that the exact `overflowed=true` value and 512-position limit survive persisted plan and evidence reconstruction. The existing assertions retain the omitted adverse proposition identity, digest, review-required goal status, and proof that planning emits no work-run artifact or execution.

The increment changes one test file only. It adds no runtime behavior, authority, inference, or execution path.

## Verification and merge

Candidate `325f3f6397378697196ea6a5df5f267fc3d92aa5` (tree `a0b20e55bcae4940cb2697dadf2b1d54d4f980a1`) was based on main `598663bb85e423072391a9e0befe24c4836af7ac`. Independent tree readback confirmed the changed test blob `31191c27be34fc6bee54645f4bbe9500072fbcca` on both the candidate and resulting main tree.

The affected staging, planning, progression, and integrated history-comparison suite passed 63 tests: 61 passed, 2 existing skips, zero failures. Compilation passed. The Mypy baseline ratchet matched 1,050 existing diagnostics, retired 40, and added zero. Exact-candidate Required Quality Gate #39384651947 passed with hosted Administrator UID 0, strict audits, audit immutability, exact acceptance, source reconstruction, and separate `pr_metadata_guard_ready`. All PR and push-triggered checks passed.

PR #2478 was merged with the regular merge method as `0b6f97752ce2da7229661174dd75fda61ae267f0`, tree `a0b20e55bcae4940cb2697dadf2b1d54d4f980a1`, ordered parents `598663bb85e423072391a9e0befe24c4836af7ac` and `325f3f6397378697196ea6a5df5f267fc3d92aa5`. GitHub reports a valid signature. Post-merge Required Quality Gate #39385084100, CI #39385084055, Codex CI #39385084097, Docker #39385084090, invariants #39385084271, and Docs Deploy #39385084088 passed; Helm, self-check, source validation, CPU smoke, and both build jobs within CI passed. Forge Smoke #39385084076 was skipped by its condition.

## Operational observation

At 2026-10-20T07:17:11Z, no scheduled Federation Health, Nightly Audit Integrity, or Nightly Self Check execution on exact main `0b6f97752ce2da7229661174dd75fda61ae267f0` was present. The latest Federation Health scheduled run remained #39378086813 on ancestor `800dcef026b32c45c5668282b260ca2e39ab4c24`; Administrator report generation succeeded, but publication failed because repository Actions policy denies Actions-token pull request creation. The latest Nightly Audit Integrity and Nightly Self Check successes remained on older heads. No current-head scheduled success is claimed.

No production inference, campaign, or transition execution was performed. Protected and stale workspaces remain untouched.

## Next dependency

Continue making persisted verified epistemic experience useful to canonical planning without weakening source identity, omission accounting, adverse-history review, or the planning/execution boundary. Reassess the bounded-priority lineage after main integration and pursue actual current-head scheduled Federation Health evidence; the next Nightly Audit Integrity and Nightly Self Check schedules are not due until their next daily window.
