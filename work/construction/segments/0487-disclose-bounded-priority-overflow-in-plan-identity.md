# Sequence 487 — disclose bounded priority overflow in plan identity

## Source increment

PR #2477 makes bounded goal tagged epistemic priority admission observable when the verified prior-projection owner is configured. The selector continues to retain at most 512 unique valid enabled proposition IDs in deterministic goal precedence order, while separately reporting whether a further unique valid enabled proposition exists. Duplicate, malformed, or disabled tags do not create a false overflow signal. The no-owner selection path keeps its previous bounded early termination and leaves the new metadata unknown.

For owner-composed planning, the overflow flag and limit are included in the canonical plan evidence binding, so they contribute to the plan ID. They are also exposed in the immutable allocation artifact and daemon planning feedback. The integrated regression proves that overflowed adverse history remains present in omission identity and keeps its goal review-required. Planning does not execute goals, emit work-run artifacts, invoke inference, or grant authority.

## Verification and merge

Candidate `0e968e7014e4929b441a922e1c2a78f85bfdfeeb` (tree `e945a199d023fcabc64d93bb5982fef08de324f7`) was based on main `157450c562dbd062ed271172f1330fa0b2df002c`. The affected staging, planning, progression, and integrated history-comparison suite passed 63 tests: 61 passed, 2 existing skips, zero failures. Compilation passed. The full Mypy baseline matched 1,050 existing diagnostics, retired 40, and added zero.

Exact-candidate Required Quality Gate #39383538468 passed. Its hosted job proved Administrator UID 0, strict audits, audit immutability, exact acceptance, source-bound reconstruction, and the separate `pr_metadata_guard_ready` status. All PR checks passed, including CI documentation, self-check, source validation, Helm, invariants, Docker, CPU smoke, and build.

PR #2477 was merged with the regular merge method as `598663bb85e423072391a9e0befe24c4836af7ac`, tree `e945a199d023fcabc64d93bb5982fef08de324f7`, ordered parents `157450c562dbd062ed271172f1330fa0b2df002c` and `0e968e7014e4929b441a922e1c2a78f85bfdfeeb`. GitHub reports a valid signature. Independent main tree readback confirmed all five changed source blobs exactly match the candidate.

Post-merge Quality Gate #39384093120, invariants #39384093116, Codex CI #39384093158, Docker #39384093138, Docs Deploy #39384093098, CI #39384093190, and Helm/source validation/self-check checks all passed. Forge Smoke #39384093187 was skipped by its workflow condition. Main now points to the merge commit and the merge tree matches the candidate tree.

## Operational observation

At 2026-10-20T07:09:00Z, no scheduled Federation Health, Nightly Audit Integrity, or Nightly Self Check run on exact main `598663bb85e423072391a9e0befe24c4836af7ac` was present. The latest Federation Health scheduled run remained #39378086813 on ancestor `800dcef026b32c45c5668282b260ca2e39ab4c24`; Administrator report generation succeeded, but publication failed because repository Actions policy denies Actions-token pull request creation. The latest Nightly Audit Integrity and Nightly Self Check successes remained on older heads. No current-head scheduled success is claimed.

No production inference, campaign, or transition execution was performed. Protected and stale workspaces remain untouched.

## Next dependency

Reopen the persisted canonical work plan and its evidence sidecar after bounded priority overflow, and verify that the overflow flag and priority limit survive exact plan and evidence readback. Keep the complete omission manifest and adverse state identity bound, and preserve planning/execution separation.
