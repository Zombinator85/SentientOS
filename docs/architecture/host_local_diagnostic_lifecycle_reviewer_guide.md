# Host-local diagnostic lifecycle reviewer guide

## Scope and non-authority boundary

This guide maps existing repository proof for one bounded host-local diagnostic
lifecycle. Admission evidence is not execution authority. Execution requires
fresh current authority, its existing operator confirmation challenge, and the
existing authority chain. Rollback separately requires fresh exact-rollback
authority and its existing operator confirmation challenge.
Closure packets are historical evidence only.

The SHA-256 digests used by these surfaces are unkeyed digests: they establish
integrity binding, not authorship or external authenticity.
No guide, receipt, packet, test, or reviewer result grants provider, network, federation-adoption,
broader host-effect, control-plane, or live-memory authority.

## Complete lifecycle map

| Stage | Purpose and required inputs | Primary module and CLI | Outputs and public validator | Authority source and exact mutation boundary | Representative focused tests |
| --- | --- | --- | --- | --- | --- |
| Host-local diagnostic execution source | Admit validated admission, dry-run, and readiness bundles plus a fresh current snapshot and verification for the fixed target. | `sentientos/host_local_diagnostic_execution_source_runtime.py`: `HostLocalDiagnosticExecutionSourceRuntimeCoordinator`; `scripts/build_host_local_diagnostic_execution_source_runtime.py` | A self-contained v2 source bundle, manifests, latest pointer, and replay index; `load_persisted_execution_source_bundle()` and `load_latest_evaluation()`. | Historical readiness plus fresh current authority is recorded, but grants no execution authority. Mutation is limited to evidence below the external source output root; the effect target is not created or changed. `tests/test_host_local_diagnostic_execution_source_runtime.py` and `tests/test_build_host_local_diagnostic_execution_source_runtime_script.py`. |
| Host-local diagnostic execution | Preflight and, after exact confirmation, perform the fixed diagnostic write using the source bundle digest, fresh snapshot and verification, execution time, challenge, and target confirmation. | `sentientos/host_local_diagnostic_execution_runtime.py`: `HostLocalDiagnosticExecutionRuntimeCoordinator`; `scripts/run_host_local_diagnostic_execution_runtime.py` | A completed execution bundle, durable intent/replay evidence, and latest pointer; `validate_persisted_execution_bundle()` and the separate `validate_live_target()`. | Fresh current authority from the v2 source/current evidence and the exact operator challenge. The effect mutation boundary is exactly the six runtime-owned files: `sentientos_local_diagnostic_effect.json`, effect receipt, postcondition, production audit, rollback plan, and transaction ledger; unrelated siblings are preserved. `tests/test_host_local_diagnostic_execution_runtime.py` and `tests/test_run_host_local_diagnostic_execution_runtime_script.py`. |
| Host-local diagnostic rollback | Revalidate a completed rollback-pending execution and current authority, preflight the exact challenge, then perform confirmed exact rollback. | `sentientos/host_local_diagnostic_rollback_runtime.py`: `HostLocalDiagnosticRollbackRuntimeCoordinator`; `scripts/run_host_local_diagnostic_rollback_runtime.py` | A completed rollback bundle, durable intent/replay evidence, and latest pointer; `validate_persisted_rollback_bundle()` and the separate `validate_live_rollback_postcondition()`. | Fresh current grant with `local_diagnostic_exact_rollback`, exact execution identity, and affirmative operator confirmation. The rollback mutation boundary is exactly deletion of `sentientos_local_diagnostic_effect.json`; no sibling or other runtime-owned file is changed. `tests/test_host_local_diagnostic_rollback_runtime.py` and `tests/test_run_host_local_diagnostic_rollback_runtime_script.py`. |
| Host-local diagnostic lifecycle closure | Package deeply validated execution and rollback bundles using both final digests and an explicit closure time. | `sentientos/host_local_diagnostic_lifecycle_closure.py`: `build_lifecycle_closure()`; `scripts/build_host_local_diagnostic_lifecycle_closure.py` | A self-contained closure packet, manifests, receipt, report, summary, and latest pointer; `validate_lifecycle_closure()` and `load_latest_summary()`. | No current runtime authority is consulted. Mutation is limited to atomic publication below the external closure output root; it never changes the live target or original bundles. `tests/test_host_local_diagnostic_lifecycle_closure.py` and `tests/test_build_host_local_diagnostic_lifecycle_closure_script.py`. |

## Operator workflow

Run from the repository root and supply operator-selected external paths and
real digests produced by the preceding validated step; this guide intentionally
does not provide fabricated digest values.

1. Prepare source evidence with `python scripts/build_host_local_diagnostic_execution_source_runtime.py evaluate` and its admission, dry-run, readiness, current-snapshot, current-verification, effect-output, and output-root arguments. Inspect it with `validate-bundle` using `--bundle-root`, then obtain the validated latest record with `latest-summary --output-root`.
2. Run execution `preflight` with `python scripts/run_host_local_diagnostic_execution_runtime.py`, including `--expected-source-bundle-digest`. Only after reviewing its challenge run `execute` with `--confirm-local-diagnostic-write`, `--confirm-source-bundle-digest`, `--confirm-effect-output-dir`, and `--confirmation-challenge-digest`. Validate the result with `validate-bundle --expected-final-bundle-digest`.
3. Run rollback `preflight` with `python scripts/run_host_local_diagnostic_rollback_runtime.py`, including `--expected-execution-bundle-digest`. Only after reviewing its challenge run `rollback` with `--confirm-exact-rollback`, `--confirm-execution-bundle-digest`, `--confirm-artifact-path`, and `--confirmation-challenge-digest`. Validate the result with `validate-bundle --expected-final-bundle-digest --expected-execution-bundle-digest`.
4. Build closure with `python scripts/build_host_local_diagnostic_lifecycle_closure.py build`, supplying `--execution-bundle-root`, `--execution-bundle-digest`, `--rollback-bundle-root`, `--rollback-bundle-digest`, `--closure-time`, and `--output-root`. Run `validate --packet-root --expected-packet-digest`, then `latest-summary --output-root` to validate both the pointer and named packet.

## Custody and lifecycle transitions

Admitted/readiness evidence becomes a self-contained source bundle but remains
non-executable evidence. Fresh authority and explicit confirmation can produce
one bounded execution and a `local_effect_lifecycle_rollback_pending`
historical lifecycle. That pending record does not itself authorize rollback.
Fresh exact-rollback authority, live-state equality, and a separate confirmation
can complete exact rollback. The paired bundles then establish the
complete-with-rollback lifecycle used to build closure.

Closure validation is historical validation, not a current authorization
decision. Because the packet contains both deeply validated bundles, it remains
self-contained after the original bundles and live target are removed.

## Failure semantics

The existing validators and coordinators fail closed for mismatched request,
execution, rollback, or correlation identity; invalid, expired, revoked, stale,
or insufficient authority; missing or contradictory confirmation; a changed
target or ambiguous invocation posture; nested bundle tampering (including an
inner reseal); closure identity or packet-path mismatch; unsafe, missing, extra,
or digest-mismatched manifest membership; and stale, substituted, or
validly-redigested contradictory latest pointers.

## Reviewer proof map

Run the existing suites from the repository root:

```bash
python -m scripts.run_tests -q tests/test_host_local_diagnostic_execution_source_runtime.py tests/test_build_host_local_diagnostic_execution_source_runtime_script.py
python -m scripts.run_tests -q tests/test_host_local_diagnostic_execution_runtime.py tests/test_run_host_local_diagnostic_execution_runtime_script.py
python -m scripts.run_tests -q tests/test_host_local_diagnostic_rollback_runtime.py tests/test_run_host_local_diagnostic_rollback_runtime_script.py
python -m scripts.run_tests -q tests/test_host_local_diagnostic_lifecycle_closure.py tests/test_build_host_local_diagnostic_lifecycle_closure_script.py
```

Representative exact behavioral nodes are:

- `tests/test_host_local_diagnostic_execution_runtime.py::test_real_execution_performs_one_bounded_transaction_and_validates_bundle`
- `tests/test_host_local_diagnostic_rollback_runtime.py::test_operator_confirmed_exact_rollback_executes_once_and_validates_bundle`
- `tests/test_host_local_diagnostic_rollback_runtime.py::test_inner_resealed_rollback_and_lifecycle_contradictions_are_rejected`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_closure_validates_after_original_bundles_and_live_target_are_deleted`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_staged_copy_is_deeply_validated_before_publication`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_concurrent_identical_builders_publish_one_valid_packet`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_interrupted_latest_publication_recovers_without_rewriting_packet`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_spawned_process_builders_publish_one_valid_closure_packet`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_process_death_before_staging_identity_publication_recovers`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_process_death_after_staging_identity_prepare_recovers`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_bootstrap_staging_reconciliation_is_bounded_and_preserves_unsafe_residue`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_process_shared_lock_waiter_is_blocked_until_owner_release`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_process_death_after_packet_rename_preserves_packet_root_and_descendants`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_bootstrap_crash_recovery_binds_one_closure_and_packet_digest`
- `tests/test_host_local_diagnostic_lifecycle_closure.py::test_validly_redigested_latest_pointer_substitution_is_rejected`
