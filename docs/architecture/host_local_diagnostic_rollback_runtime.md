# Host-local diagnostic rollback runtime

This runtime closes only a completed host-local diagnostic execution whose
transaction lifecycle is `local_effect_lifecycle_rollback_pending`. It deeply
validates the immutable execution bundle, requires its externally supplied
final digest, revalidates current grant, expiry, revocation and the explicit
`local_diagnostic_exact_rollback` scope, and compares every runtime-owned live
file with its historical snapshot.

Preflight is read-only and produces an exact confirmation challenge. Execution
requires affirmative confirmation of the bundle digest, artifact path and
challenge digest. The coordinator delegates the sole mutation to
`run_local_diagnostic_exact_rollback_wing`; its mutation set is exactly
`sentientos_local_diagnostic_effect.json`. It never implements deletion itself.

A cross-process lock and fsynced intent chain commit invocation before the
primitive call. A returned complete rollback can be reconciled, while an
invocation-committed or incomplete observation is permanently ambiguous and is
never retried. Completed bundles replay without the execution bundle or live
artifact. Historical validation is independent of live state; the separate
live-postcondition validator checks the artifact remains absent and all other
runtime-owned files still match.

No general cleanup, recursive or wildcard deletion, sibling mutation,
subprocess, shell, network, provider, prompt, daemon, dashboard, hardware, or
control-plane execution authority is introduced.
