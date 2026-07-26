# Host local diagnostic execution-source runtime

New packages use schema `host_local_diagnostic_execution_source_runtime.v2`.
Schema v1 is retained only as `LEGACY_SCHEMA_VERSION` and is rejected rather
than upgraded or reinterpreted. The public semantic validator replays persisted
records without consulting original source directories. Publication and replay
are guarded by a cross-process filesystem lock. Manifest entries bind schema,
kind, size, digest, and semantic identity, while lexical path components are
checked before resolution so traversed symlinks remain visible.

This runtime closes the provenance gap between persisted real-effect admission,
dry-run execution, executor readiness, and a **fresh current** host-local
authorization snapshot. It produces one self-contained, replay-safe source
custody package for the existing bounded diagnostic target. The package is
metadata only: it neither authorizes execution nor invokes a runner, backend,
control plane, subprocess, network path, or local diagnostic effect.

## Exact custody chain

`evaluate` accepts only bundles accepted by the public persisted validators for
`host_real_effect_admission_runtime.v1`, `host_dry_run_execution_runtime.v1`,
and `host_fulfillment_executor_readiness_runtime.v1`. It binds the admission
candidate, decision and implementation-plan scaffold to the embedded closure;
the closure to the exact dry-run receipt; and the dry-run request and runtime
receipt to the readiness receipt, executor contract, declarative plan, and
canonical diagnostics route. Blocked, contradicted, warning-substituted, loose,
or tampered evidence fails closed.

Current authority is not inferred from historical readiness. The supplied
snapshot is checked by `validate_current_authority_snapshot()`, including the
exact grant bytes and host-local issue receipt. The supplied grant verification
must be positive, cover every required scope, and report no missing labels.
Expiry and revocation posture are copied from the validated snapshot; omitted
revocation evidence, expiry, revocation, staleness, or substitution blocks the
package.

## Target and persistence boundary

The only represented target is `diagnostics_local_file_effect` using
`diagnostic_write_with_ledger`, artifact
`sentientos_local_diagnostic_effect.json`, without force overwrite or rollback
execution. Repository-local, root, symlinked, traversal, overlapping, or
already-populated targets are rejected. The target directory is never created.
Evidence is written atomically beneath a separate external root with content
and final manifests, latest pointer, and correlation replay index.

`validate-bundle` and `latest-summary` are read-only. Deep validation rejects
manifest, path, digest, schema, lineage, target, authority, and positive effect
flag substitutions. Replay reads the custody package alone and performs no new
writes. Reusing a correlation ID with different source, authority, or target
semantics returns a deterministic conflict.

## CLI

```text
python scripts/build_host_local_diagnostic_execution_source_runtime.py evaluate \
  --admission-bundle-root /external/admission/ID \
  --dry-run-bundle-root /external/dry-run/ID \
  --readiness-bundle-root /external/readiness/ID \
  --current-snapshot-json /external/current-snapshot.json \
  --current-verification-json /external/current-verification.json \
  --effect-output-dir /external/future-effect \
  --output-root /external/execution-source
python scripts/build_host_local_diagnostic_execution_source_runtime.py validate-bundle --bundle-root /external/execution-source/ID
python scripts/build_host_local_diagnostic_execution_source_runtime.py latest-summary --output-root /external/execution-source
```

Any later real-write runtime remains a separate, explicitly operator-confirmed
task and must revalidate current authority immediately before its write.
