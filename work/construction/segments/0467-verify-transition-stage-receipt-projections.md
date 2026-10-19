# Sequence 467 — Verify transition-stage receipt projections

## Source increment

Starting from verified main `7d248f8320da2de7bfe4513afc517de93f47ab05`, direct hosted receipt tests exposed two defects. Ordinary processing stores the controller result directly in receipt detail, while the projection expected a nested `stage_result`; and recovery compared the completed phase to the attempt phase even though the journal records prior and requested phases separately.

The fix accepts the direct result shape (and preserves compatibility with nested projections). It validates completed journal rows against the requested stage, failed rows against the attempted phase, and rejects other terminal statuses and phase mismatches. Projection remains read-only and grants no authority.

## Verification and merge

The first candidate `cb93b2d921b9eccd30ee2973f348ca916a0ab112` correctly exposed two failed tests and was not submitted as a PR. Corrected candidate `f3346dcfb689a3f96394c9206dea615ee8b19956` passed the three exact receipt regressions in Source Validation run #39291354656: ordinary completed binding, journal-recovered completion, and rejected or missing custody. Exact-candidate provenance reported 3 passed, 0 failed, `validation_complete`; acceptance was `task_acceptance_ready`. Source artifact #12204494581 SHA-256: `4ee8ad174a7129ed059cadea2069c1c43c5324470911b83e76f1fdb0d16772c5`.

The hosted Administrator finalizer and separate pre-publication metadata guard passed in Required Quality Gate run #39291963006 (`ready_to_commit`, `pr_metadata_guard_ready`; solo profile, exhaustive matrix not requested). PR #2437 passed all applicable PR checks and merged with history preserved. Main is `9dea3d044cdc2f8a6dde9e0a4d37b2fb37d74a22`, tree `e7ec31c361da63d5a19c3f2d32a1eddea7af8497`, parents `7d248f8320da2de7bfe4513afc517de93f47ab05` and `f3346dcfb689a3f96394c9206dea615ee8b19956`. Post-merge quality gate #39292586771, invariants #39292586769, build/deploy #39292586801 and #39292586759, CPU smoke #39292586802, and docs, Helm, self-check, and source validation #39292586865 passed. Forge Smoke #39292586800 was skipped by workflow condition.

## Federation Health

Scheduled run #39279382936 executed on the pre-merge main head `7d248f8320da2de7bfe4513afc517de93f47ab05`. Its privileged health update, execution binding, and artifact upload succeeded. Artifact #12200206840 SHA-256: `a0e5c02b2f9f4a6b89f28a23e7bb02e8b7936fb5b478724c40d59e037ea6fdc0`. The separate publication job failed because repository policy forbids Actions from creating or approving PRs. The workflow token already had only declared `contents:write` and `pull-requests:write`; widening token permissions cannot fix this repository-level setting. No current-main scheduled execution after this merge has been observed.

## Next dependency and limits

Next, connect the daemon's one-stage verified receipt observation to the developmental campaign progression owner, retaining preregistered approvals and terminal interruption behavior. This sequence adds verification coverage only; it enables no campaign executor.

Historical provenance remains `INTEGRITY_BROKEN`; sequence-286 loss remains explicit. No campaign execution, readiness, synthetic rehearsal, production trial, or authority grant is claimed. Protected and stale workspaces were not modified. The available GitHub connector cannot change repository settings; automated PR publication needs an authorized least-privilege GitHub App or administrator-approved setting.
