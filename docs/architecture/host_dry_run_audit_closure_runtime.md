# Host Dry-Run Audit Closure Runtime

The host dry-run audit closure runtime binds the exact persisted bundle emitted by
`sentientos/host_dry_run_execution_runtime.py` to the metadata-only dry-run audit
closure records in `sentientos/dry_run_audit_closure.py`.

It is a closure and custody surface only. It does not request real-effect
admission, execution admission, fulfillment authority, real backend loading,
provider invocation, network access, subprocess or shell execution, repository
mutation, Git mutation, host mutation, real postcondition checks, real rollback,
or production audit receipts.

## Required source bundle

The runtime accepts only an already-persisted host dry-run execution runtime
bundle. Strict validation checks the source content manifest, final bundle
manifest, required artifact sizes and hashes, source request and plan,
simulation admission, harness policy, simulated backend registry, dry-run
request, dry-run result, successful `DryRunExecutionReceipt`, host dry-run
runtime receipt, direct parent IDs and digests, domain validators,
`simulation_only=true`, `dry_run_executed=true`, and all no-real-effect flags.

Standalone dry-run receipts, standalone runtime receipts, loose JSON,
reconstructed IDs or digests, blocked or incomplete sources, stale sources,
contradicted sources, missing sources, and tampered bundles fail closed.

## Closure records and parent lineage

The existing dry-run audit closure builders remain the source of record for
closure domain records. The runtime hardens their lineage with direct parent ID
and digest binding:

- effect verification binds to the dry-run receipt;
- postcondition verification binds to the dry-run receipt and effect
  verification;
- rollback rehearsal binds to the dry-run receipt and effect verification;
- audit closure receipt binds to the dry-run receipt, effect verification,
  postcondition verification, and rollback rehearsal;
- closure bundle binds to all closure records.

Custody timestamps such as `created_at` are excluded from semantic digests, so
replay custody time does not change identities. Changing semantic parent lineage
changes dependent identities.

## Persistence and replay

Bundles are written below an external output root using atomic replacement and a
filesystem lock. Repository-local runtime roots, symlink escapes, traversal, and
oversized/unknown artifacts are rejected. The bundle includes request, source
manifest, source-bundle reference, plan, dry-run effect verification, simulated
postcondition verification, simulated rollback rehearsal, audit closure receipt,
closure bundle, validation findings, runtime receipt, content manifest, final
bundle manifest, summary, deterministic Markdown, latest pointer, and replay
index.

Exact replay reads existing artifacts and performs zero new closure builder work.
Identical concurrent requests converge on one bundle. Differing requests sharing
a correlation ID are deterministic semantic conflicts. Corrupt prior bundles are
rejected.

## Daemon and dashboard projection

`sentientosd` and the dashboard only read already-persisted, deeply validated
closure evidence. They do not select source bundles, construct closure records,
or invoke the runtime. The authenticated dashboard route is:

```http
GET /api/world-state/host-dry-run-audit-closure
```

Projected World-State evidence preserves `metadata_only=true`,
`simulation_only=true`, and false flags for production audit receipts, real
effect receipts, real postcondition checks, real rollback, real fulfillment,
real effects, real backend invocation, and host mutation.

## Persisted bundle validation repair

The dry-run source runtime and the audit-closure runtime now treat persisted
bundles as custody artifacts rather than convenient JSON directories.  Public
read-only validators validate the originally supplied root before resolving it,
reject symlink roots and symlink artifact files, require exact manifest
membership, reject duplicate manifest entries, missing manifested files,
required semantic artifacts omitted from manifests, and unexpected unmanifested
semantic JSON artifacts, and bind both content and final manifests to recorded
sizes and SHA-256 file digests.

The non-self-referential digest structure is: the content manifest binds the
semantic artifacts, the runtime receipt binds the content-manifest digest, the
final manifest binds the content manifest plus runtime receipt, and latest.json
or replay_index.json bind the final-manifest digest.  The runtime receipt no
longer assigns meaning to an always-empty final bundle digest.

CLI validation commands are read-only.  `validate-source` uses the source bundle
validator, `validate-bundle` uses the closure bundle validator, and
`validate-evaluation` remains only an in-memory diagnostic.  Invalid persisted
evidence exits nonzero.  Daemon world-state projection follows only the public
validated latest-bundle loader; corrupted latest evidence is unavailable rather
than promoted into a positive World-State fact.

## Strict v2 persisted semantic custody

New strict closure bundles use `host_dry_run_audit_closure_runtime.v2` and embed the already validated source dry-run execution receipt as `source_dry_run_receipt.json`. Strict replay validates that embedded receipt with the dry-run execution receipt domain validator and binds its exact ID/digest through the source runtime receipt, closure request, closure runtime receipt, and dry-run audit closure chain. The original source bundle path remains informational for reviewers; strict replay and persisted validation do not reread `dry_run_receipt.json` through that mutable path.

The source dry-run execution bundle loader also revalidates persisted semantic custody beyond file digests: request/plan linkage, simulation admission posture, canonical inert harness policy, simulated backend registry domain posture, backend/domain agreement, dry-run request/result/receipt validators, exact runtime parent IDs and digests, successful-result-only persistence, and every no-real-effect assertion. Recomputing a tampered record's digest and manifests is therefore insufficient to make semantic substitution valid.
