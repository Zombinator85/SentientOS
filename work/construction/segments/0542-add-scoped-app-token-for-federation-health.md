# Sequence 542 — add a scoped App token for Federation Health checks

The Federation Health publisher's successful scheduled runs could create or update its report PR, but PR checks created with `GITHUB_TOKEN` remained in GitHub's `action_required` state. The publisher can now optionally use a GitHub App installation token. The opt-in App action is pinned to commit `64ab729a6294000f5aa4a4bc0b73d1f32bc45510`, runs on Node 24, is scoped to `Zombinator85/SentientOS`, and requests only `contents: write` and `pull-requests: write`. With the repository variable unset, the existing `GITHUB_TOKEN` path remains unchanged. No Actions permission or approval bypass was added.

The optional repository variable and secret names, App installation scope, and required permissions are documented in `docs/federation_health_publication.md`. No App credential is configured or included in this change. The existing automated report PR remains unapproved and unmerged pending checks.

Local verification: the workflow parsed as YAML; direct source inspection confirmed repository scoping, the two requested App permissions, unchanged publisher job permissions, and the explicit token fallback. The changed test module compiled and `git diff --check` passed. The two focused pytest nodes did not execute: the canonical test-airlock bootstrap could not download its pinned build dependency in this network-restricted sandbox, and direct pytest was correctly stopped by the repository's conftest guard. No local test pass is claimed. Exact-candidate hosted verification is pending.

The source candidate `d202a441c7a67da2769ff66bfacc4d02a727d5bd`, tree `e74884090c58da73d333e3265820fa960609fe9e`, is parented to verified main `20509f3cd7ee7d28b08bf3abc6e6a445fd3f0f7a`, tree `ce98c6d030b62d81a82598900d0bad5e445223b8`. GitHub independently returned the same commit parent and tree, and each of the five changed file blobs matched its local Git blob identity.

Post-merge CI on main run `39597589541` completed successfully, including full pytest, the Mypy baseline ratchet, Helm integration, source validation, and the Sphinx linkcheck. Required Quality Gate `39597589527`, Docker `39597589660`, Docs Deploy `39597589636`, Invariant Tests `39597589574`, and Codex CI `39597589749` also passed. Forge Smoke `39597589532` was skipped by its configured condition. The scheduled Federation Health workflow has not produced a run on this main: the latest listed scheduled execution remains run `39582634969`, before the merge. Bot PR #2511 still has no approved PR checks and is not represented as verified.

No production model transition, activation, serving, inference, or writeback was performed.

Verified base main: `20509f3cd7ee7d28b08bf3abc6e6a445fd3f0f7a`, tree `ce98c6d030b62d81a82598900d0bad5e445223b8`
Implementation candidate: `d202a441c7a67da2769ff66bfacc4d02a727d5bd`, tree `e74884090c58da73d333e3265820fa960609fe9e`
Latest construction segment: `work/construction/segments/0542-add-scoped-app-token-for-federation-health.md`
Sequence: 542 (candidate pending hosted verification)
