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
