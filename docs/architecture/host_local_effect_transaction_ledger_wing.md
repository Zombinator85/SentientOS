# Host Local Effect Transaction Ledger Wing

This wing follows the [Host Local Diagnostic Exact Artifact Rollback Pilot Wing](host_local_diagnostic_exact_rollback_pilot_wing.md). The exact rollback pilot proved that the first intentionally real local diagnostic artifact write can be reversed by an explicit, exact-artifact-only rollback. This wing connects those formerly loose records into a metadata-only transaction ledger.

## Boundary

The ledger does **not** introduce a new host effect. It does not run the diagnostic effect. It does not run rollback. It does not delete files except for the optional explicit write of one caller-supplied ledger JSON artifact path.

It is not general cleanup and is not broader host control. It does not perform fan/PWM writes, thermal actuation, power profile mutation, service restart, process killing, package installation, driver installation, network egress, provider invocation, prompt assembly/export, subprocess execution, shell execution, OS-backend invocation, control-plane execution, federation transport/sync/adoption, or remote execution.

## What the ledger records

`sentientos/local_effect_transaction_ledger.py` creates immutable-style metadata records for the bounded local diagnostic lifecycle:

- `LocalEffectTransactionEntry` records one source event, source record digest, previous entry digest, event kind, blocked actions, warnings, risks, and no-new-effect flags.
- `LocalEffectTransactionLedger` orders entries into a digest chain and stores the current transaction status plus effect receipt, postcondition, production audit, rollback plan, rollback receipt, rollback postcondition, and rollback audit identifiers.
- `LocalEffectTransactionLifecycleReport` classifies lifecycle posture from the ledger.
- `LocalEffectTransactionLedgerArtifactReceipt` records the optional explicit ledger artifact write when a caller supplies an output path.

## Lifecycle classification

The wing detects and reports:

- open or rollback-pending transactions when the effect, postcondition, audit, and rollback plan exist but no rollback receipt exists yet;
- orphaned effects when an effect receipt is present without its postcondition or production audit;
- incomplete rollback when rollback exists without rollback postcondition or rollback audit;
- contradicted transactions when duplicate event kinds, digest mismatches, or forbidden host/network/provider/prompt/subprocess/shell/hardware/service/power/fan/thermal/general-cleanup claims appear;
- closed transactions only when the effect receipt, effect postcondition, production audit, rollback plan, rollback receipt, rollback postcondition, and rollback audit are present and non-contradictory.

## CLI

Build a metadata-only ledger from explicit record files without running effect or rollback:

```bash
python scripts/build_local_effect_transaction_ledger.py --effect-receipt /tmp/sentientos-local-diagnostic-effect/effect_receipt.json --postcondition-check /tmp/sentientos-local-diagnostic-effect/postcondition_check.json --production-audit /tmp/sentientos-local-diagnostic-effect/production_audit.json --rollback-plan /tmp/sentientos-local-diagnostic-effect/rollback_plan.json --summary
```

After exact rollback, include rollback records for a closed transaction:

```bash
python scripts/build_local_effect_transaction_ledger.py --effect-receipt /tmp/sentientos-local-diagnostic-effect/effect_receipt.json --postcondition-check /tmp/sentientos-local-diagnostic-effect/postcondition_check.json --production-audit /tmp/sentientos-local-diagnostic-effect/production_audit.json --rollback-plan /tmp/sentientos-local-diagnostic-effect/rollback_plan.json --rollback-receipt /tmp/sentientos-local-diagnostic-effect/rollback_receipt.json --rollback-postcondition-check /tmp/sentientos-local-diagnostic-effect/rollback_postcondition_check.json --rollback-audit /tmp/sentientos-local-diagnostic-effect/rollback_audit.json --summary
```

`--output PATH` writes one deterministic ledger artifact only to that explicit file path. Directory and filesystem-root outputs are refused, and existing files require `--force`.

## Reviewer proof bundle posture

The reviewer proof bundle includes `local_effect_transaction_ledger_capability.json` and lists the CLI command in `proof_commands.json` as `proof_command_not_run`. Bundle generation does not run the diagnostic effect, rollback, or transaction ledger by default.

## Capability registry posture

The capability registry marks `local_effect_transaction_ledger`, `local_effect_lifecycle_report`, and `local_effect_transaction_ledger_artifact` as implemented bounded metadata surfaces. `general_effect_transaction_ledger` remains deferred. General cleanup, recursive delete, unrelated file delete, fan/PWM, thermal, power, service, package, driver, network, provider, prompt, federation, remote execution, subprocess, shell, OS backend, and control-plane execution remain blocked or deferred.

## Implementation links

- Module: `sentientos/local_effect_transaction_ledger.py`
- CLI: `scripts/build_local_effect_transaction_ledger.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_local_effect_transaction_ledger.py`, `tests/test_build_local_effect_transaction_ledger_script.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.

## Built-In Runner Link

`docs/architecture/host_builtin_local_effect_runner_pilot_wing.md` preserves transaction ledger compatibility by emitting effect receipt, postcondition, production audit, and rollback plan paths, but it does not automatically build the ledger.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.
