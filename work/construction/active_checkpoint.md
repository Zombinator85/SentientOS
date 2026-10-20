# Active construction checkpoint

## Latest verified main

PR #2452 carried installation-verified operator identity from the live resident-transition request and verified stage receipt into the canonical read-only campaign plan and active-trial binding. The v3 receipt projection re-verifies exact signed request provenance against the installation-pinned trust catalog. The plan validates and digest-binds the bounded principal record, including operator/key identifiers, request and provenance digests, signed time, and pinned catalog version/digest. Nested identity data remains immutable; daemon adapters return JSON-safe snapshots; legacy projections without authenticated identity fail closed.

This provenance remains descriptive. Planning does not execute goals, mint or select approvals, advance campaign state, process request mailboxes, or grant authority. Independent stage-owner validation and separately supplied approvals remain required. No production trust catalog or key material was provisioned.

Candidate `23c37a85ea33a74ca278213d7be9584acfd3abc8` (tree `200e043067dd13350d3ec338762e48fade5d7e01`) passed 200 local affected tests, compilation, whitespace checks, and exact-base Mypy comparison with zero new diagnostics and 40 retired baseline diagnostics. All seven changed GitHub blobs were independently read back. Exact-candidate hosted Quality Gate #39344680427 passed Administrator strict audits and immutability verification, both finalizers, exact candidate acceptance, and the separate metadata guard bound to the candidate head/tree. The guard returned `pr_metadata_guard_ready`; the solo profile was used and exhaustive matrix execution was not requested. Full PR CI, Docker, Codex CI, Release, Gradient, lint, invariants, and Quality Gate passed.

PR #2452 merged regularly as `37497cb07803b250b6370d35ac4e14b7115aa7c9`, tree `200e043067dd13350d3ec338762e48fade5d7e01`, ordered parents `18e31f5ba893114161dfa3fe5866d18183f720d6` and `23c37a85ea33a74ca278213d7be9584acfd3abc8`. Post-merge Quality Gate #39345078877, invariants #39345078909, Codex CI #39345078938, Docs Deploy #39345078941, Docker #39345078856, and CI #39345078875 passed. The CI source-validation, Helm integration, self-check, and Sphinx external link-check jobs passed. Forge Smoke #39345078997 was skipped by its workflow condition.

## Open evidence boundaries

- Authenticated operator identity is now carried into canonical planning. A useful next increment is to retain appropriately minimized provenance in append-only stage outcome evidence, without turning identity into authority.
- No production operator trust catalog or private signing key is included. No production request, production campaign execution, or temporal A-to-B-to-A transition has been exercised.
- The scheduled Federation Health execution on the new main has not yet been observed. Its publication job may still require the Actions PR-creation setting or an approved least-privilege GitHub App credential. Audit Nightly and Nightly Self Check schedules remain to be observed.
- Historical test provenance remains INTEGRITY_BROKEN; sequence-286 loss remains explicit.
- Sequence-382 through sequence-386 work and protected stale workspaces remain untouched.

Latest verified main: `37497cb07803b250b6370d35ac4e14b7115aa7c9`, tree `200e043067dd13350d3ec338762e48fade5d7e01`
Latest construction segment: work/construction/segments/0474-carry-authenticated-operator-identity-into-canonical-planning.md
Latest segment SHA-256: `c872b76685dca0d26181cd1cd854a8f1ae3c85d251cf177589978bc0f353b4dc`
Sequence: 474 (verified operator identity is bound into canonical planning; authority remains with independent stage owners)
