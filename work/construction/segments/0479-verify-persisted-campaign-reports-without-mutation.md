# Sequence 479 — Verify persisted campaign reports without mutation

## Source increment

PR #2461 adds a read-only API and CLI for verifying an existing completed campaign report against canonical campaign state and immutable trial receipt, protocol, and transition-stage bindings. It checks exact report bytes and digests and retains historical v1 report support. Verification does not create or recover reports, repair state, execute trials, or grant authority.

## Verification and merge

The focused local suite passed (95 tests, zero failures); compilation, workflow YAML parsing, and the Mypy baseline ratchet passed with zero new errors. A larger local suite was interrupted, so no local full-suite result is claimed. Hosted CI, Required Quality Gate, Codex CI, lint, Docker, release validation, and invariants passed on the exact candidate. Hosted self-check reported 143 passed, 13 skipped, zero failures. Hosted strict Administrator audits, audit immutability, exact task acceptance, and the separate prepublication metadata guard passed.

PR #2461 candidate `fa697b515176e9ceab02de8f81520b554cd71d77` (tree `118dc8d56abb4536b3499a104a009561e5dfdd0d`), based on `1baef37e6ac608f018b595123c86930d1f616a7c`, was regular-merged as `5164520ece5820b525942e3b57e56ebbbd0b24f3` (tree `118dc8d56abb4536b3499a104a009561e5dfdd0d`), preserving candidate history. The post-merge Quality Gate, Codex CI, Docker, and docs deployment passed on the exact main SHA; the post-merge Quality Gate artifact verified effective UID 0, strict audits, and immutability. Standard post-merge CI was still in progress at this evidence capture.

## Current operational evidence

At 2026-10-20T03:22:03Z, GitHub Actions had not recorded a post-merge Federation Health, Nightly Audit Integrity, or Nightly Self Check run on main `5164520ece5820b525942e3b57e56ebbbd0b24f3`. The standard post-merge CI run #39363578405 remained in progress. These are pending observations, not inferred passes.

## Next dependency

Continue closing the feedback loop from retained, verified experience into canonical planning while keeping report verification read-only and preserving the separation between planning and execution. Production campaign execution, inference, request execution, operator catalog provisioning, and private signing-key shipment remain absent; protected and stale workspaces remain untouched.
