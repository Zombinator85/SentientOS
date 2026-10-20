# Sequence 478 — Expose verified transition provenance in campaign reports

## Source increment

PR #2460 adds descriptive provenance to completed production self-reflection campaign reports. New v2 reports include the exact campaign protocol digest and minimal per-trial provenance so retained outcomes can be correlated with verified transition bindings. Historical v1 report output remains byte-stable. The addition does not score outcomes or change approval, authority, inference, or transition behavior.

## Verification and merge

The local campaign regressions passed (75 passed, zero failures, errors, or skips); compilation and workflow YAML parsing passed. The Mypy baseline ratchet reported zero new errors and 40 retired baseline errors. Hosted source validation, CI, and Required Quality Gate passed on the exact candidate. The hosted gate verified Administrator audits, audit immutability, exact task acceptance, and the separate prepublication metadata guard. Post-merge CI, Quality Gate, Codex CI, invariants, Docker, and docs deployment passed on main.

PR #2460 candidate `3367e9f8f858d73d4b5d2be420afd705cf3dbd6e` (tree `7641acfa3e8f7d719cd3707693425f4b8278fd90`), based on `d3420704c90796d16fe4e393170f7fb1076eb10f`, was regular-merged as `1baef37e6ac608f018b595123c86930d1f616a7c` (tree `b0bbd779fcd9e803b2b6cdbebe82eb50f6cd1f68`), preserving the candidate commit as second parent. GitHub tree and blob readback matched all five changed blobs.

## Current operational evidence

At 2026-10-20T03:22:03Z, current main is `1baef37e6ac608f018b595123c86930d1f616a7c`. No post-merge Federation Health, Nightly Audit Integrity, or Nightly Self Check run on that exact head is present. Older schedule runs do not establish current-head execution.

## Next dependency

Provide a read-only way to validate persisted reports against canonical campaign state and immutable trial evidence, without recovery or mutation. Production campaign execution, inference, request execution, operator catalog provisioning, and private signing-key shipment remain absent; protected and stale workspaces remain untouched.
