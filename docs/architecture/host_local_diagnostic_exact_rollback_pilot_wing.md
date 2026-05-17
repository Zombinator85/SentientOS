# Host Local Diagnostic Exact Artifact Rollback Pilot Wing

This wing follows the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md). The previous wing proved one bounded real local artifact write. This wing proves the matching bounded rollback for that exact artifact only.

## Boundary

This is the first intentionally real rollback pilot. Its only allowed real effect is deleting the exact diagnostic artifact created by `sentientos/local_diagnostic_effect.py` and recorded by the local diagnostic effect receipt plus rollback plan.

It is not general cleanup. It is not directory cleanup. It is not recursive deletion. It is not wildcard deletion. It is not unrelated file deletion. It does not delete siblings, parent directories, temporary directories, or any path other than the exact recorded artifact path.

Before `Path.unlink()` is reached, the rollback verifies all of the following:

- the source effect receipt succeeded;
- the rollback plan references the same receipt and output path;
- the output path is inside the explicit `--output-dir-scope`;
- the scope is not filesystem root;
- the target path is not root, not a directory, and not a symlink;
- the observed artifact digest matches the expected digest from the effect receipt.

Hardware, service, power, process, package, driver, network, provider, prompt, subprocess, shell, OS-backend, control-plane, federation transport/sync/adoption, and remote execution actions remain forbidden.

## Records

- **LocalDiagnosticExactRollbackRequest** records the source effect receipt, source rollback plan, expected artifact path/digest, explicit output scope, blocked actions, and false network/provider/prompt/subprocess/shell flags.
- **LocalDiagnosticExactRollbackResult** records whether exact artifact deletion happened. `real_rollback_performed=true`, `file_delete_performed=true`, and `host_mutation_performed=true` only when the exact artifact path is deleted.
- **LocalDiagnosticExactRollbackReceipt** records exact-artifact-only rollback evidence and keeps general cleanup, directory cleanup, recursive delete, wildcard delete, unrelated delete, hardware, service, network, provider, and prompt flags false.
- **LocalDiagnosticRollbackPostconditionCheck** verifies the exact artifact path is absent and performs no host mutation.
- **LocalDiagnosticRollbackAuditReceipt** records production rollback audit evidence for the exact local diagnostic artifact only.

## CLI

First run the explicit diagnostic effect pilot so the receipt and rollback plan files are written:

```bash
python scripts/run_local_diagnostic_effect.py --output-dir /tmp/sentientos-local-diagnostic-effect --summary --force
```

Dry-run rollback validates the exact path and digest but does not delete:

```bash
python scripts/run_local_diagnostic_rollback.py --effect-receipt /tmp/sentientos-local-diagnostic-effect/effect_receipt.json --rollback-plan /tmp/sentientos-local-diagnostic-effect/rollback_plan.json --output-dir-scope /tmp/sentientos-local-diagnostic-effect --dry-run --summary
```

Real rollback is explicit and deletes only the exact diagnostic artifact:

```bash
python scripts/run_local_diagnostic_rollback.py --effect-receipt /tmp/sentientos-local-diagnostic-effect/effect_receipt.json --rollback-plan /tmp/sentientos-local-diagnostic-effect/rollback_plan.json --output-dir-scope /tmp/sentientos-local-diagnostic-effect --summary
```

`--allow-missing-artifact` records that no deletion was performed when the exact artifact is already absent. It does not widen scope and does not become cleanup.

## Reviewer proof bundle posture

The reviewer proof bundle documents this capability in `local_diagnostic_rollback_capability.json` and lists the rollback CLI in `proof_commands.json` as `proof_command_not_run`. The proof bundle does not run the effect or rollback by default and remains no-real-effect/no-host-mutation by default.

## Capability registry posture

The capability registry marks `local_diagnostic_exact_rollback`, `local_diagnostic_rollback_postcondition_check`, and `local_diagnostic_rollback_audit_receipt` as implemented exact-artifact-only surfaces. General file cleanup, recursive delete, unrelated delete, fan/PWM control, thermal actuation, power mutation, service restart, package/driver install, provider/network/prompt/federation/remote execution remain blocked or deferred.

## Implementation links

- Module: `sentientos/local_diagnostic_effect.py`
- CLI: `scripts/run_local_diagnostic_rollback.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_local_diagnostic_exact_rollback.py`, `tests/test_run_local_diagnostic_rollback_script.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

Next: [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md) connects the effect, rollback, postcondition, and audit records into a metadata-only transaction lifecycle ledger.

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.

## Built-In Runner Link

`docs/architecture/host_builtin_local_effect_runner_pilot_wing.md` may invoke this exact-artifact rollback path in-process only; it does not broaden cleanup, recursive delete, or unrelated file deletion.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.
