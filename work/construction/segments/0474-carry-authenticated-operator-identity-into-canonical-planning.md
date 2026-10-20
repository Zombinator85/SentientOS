# Sequence 474 — Carry authenticated operator identity into canonical planning

## Source increment

Starting from verified main `18e31f5ba893114161dfa3fe5866d18183f720d6`, this increment connects the authenticated operator provenance established at live request admission to the daemon's verified stage-receipt projection and the canonical production self-reflection plan.

The receipt projection now uses a v3 schema and re-verifies the exact signed request provenance against the installation-pinned trust catalog. It carries a bounded identity record: operator and signing-key identifiers, request-claims and provenance digests, signed time, and the pinned trust-catalog version and digest. The planner validates that shape, binds it into its read-only plan and active-trial binding, and rejects older projections that lack authenticated identity.

Nested identity metadata remains recursively immutable inside canonical plans. Daemon adapters return recursive plain snapshots so the read-only projection remains JSON serializable at the transport boundary. The provenance is descriptive: it does not select or mint stage approvals, advance campaign state, process request mailboxes, grant authority, or execute goals. Existing live-owner and independent stage-approval checks remain in force.

## Local verification

The canonical runner passed 200 affected tests across the operator authentication/trust catalog, resident transition operator, production self-reflection campaign and CLI, transition experiment and capability admission, and daemon composition. Touched modules compiled, `git diff --check` passed, and the Mypy baseline comparison reported zero new diagnostics, 40 retired baseline diagnostics, and 1,050 matched existing diagnostics.

## Hosted verification and merge

Candidate `23c37a85ea33a74ca278213d7be9584acfd3abc8` has tree `200e043067dd13350d3ec338762e48fade5d7e01`, with two source commits based on verified main `18e31f5ba893114161dfa3fe5866d18183f720d6`. All seven changed blobs were independently read back from GitHub and matched the candidate tree.

The exact-candidate hosted Required Quality Gate #39344680427 succeeded. Its artifacts bind the finalizer and separate metadata guard to head `23c37a85ea33a74ca278213d7be9584acfd3abc8` and tree `200e043067dd13350d3ec338762e48fade5d7e01`; the metadata guard returned `pr_metadata_guard_ready`. Hosted Administrator verification reported strict audit and immutability checks passed with `administrator_verified=true`. The gate used the solo profile; exhaustive matrix execution was not requested.

PR #2452 passed CI #39344664200, Docker #39344664179, Codex CI #39344664191, Release #39344664199, Gradient null regression #39344664206, Lint Benchmark #39344664258, Invariant Tests #39344664188, and the Required Quality Gate. It was merged using the regular merge method with expected head `23c37a85ea33a74ca278213d7be9584acfd3abc8`.

Main now points to merge commit `37497cb07803b250b6370d35ac4e14b7115aa7c9`, tree `200e043067dd13350d3ec338762e48fade5d7e01`, with ordered parents `18e31f5ba893114161dfa3fe5866d18183f720d6` and `23c37a85ea33a74ca278213d7be9584acfd3abc8`. Post-merge Required Quality Gate #39345078877, Invariant Tests #39345078909, Codex CI #39345078938, Docs Deploy #39345078941, Docker #39345078856, and CI #39345078875 all succeeded. The CI source-validation, Helm integration, self-check, and Sphinx external link-check jobs passed. Forge Smoke #39345078997 was skipped by its workflow condition.

The first sequence-evidence candidate's CI #39345891304 correctly rejected an out-of-sync checkpoint blob after the checkpoint text was refreshed but its stored GitHub content was stale. The checkpoint and index are being corrected together; the failed guard was preserved and not waived.

## Next dependency and limits

The authenticated principal is now carried into planning, but no production operator catalog, private signing key, live production request, or production campaign execution is present. A later increment should establish how this provenance is retained in append-only stage outcome evidence without turning operator identity into authority or exposing unnecessary personal data.

The post-merge scheduled Federation Health execution on this main has not yet been observed. Historical test provenance remains integrity-broken, and the sequence-286 loss remains unresolved. Protected stale workspaces remain untouched.
