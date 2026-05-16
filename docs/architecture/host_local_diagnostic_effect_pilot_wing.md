# Host Local Diagnostic Effect Pilot Wing

This wing follows the [Host Real Effect Capability Admission Wing](host_real_effect_capability_admission_wing.md). It is the first intentionally real effect pilot after real-effect admission: a deliberately narrow, explicit, local-only diagnostic artifact write.

## Boundary

The only real effect is writing one deterministic metadata/diagnostic artifact to an explicit caller-supplied local output directory. The write is optional, happens only through `sentientos/local_diagnostic_effect.py` APIs or the explicit CLI, and is not performed at import time or during reviewer proof bundle generation.

This is not general host control. It does not create general host executors, OS backends, provider paths, network paths, prompt export paths, federation transport, remote execution, subprocess execution, shell execution, fan/PWM control, thermal actuation, power profile mutation, service restart, process killing, package installation, driver installation, or cleanup of unrelated files. In direct terms: no network egress, no provider invocation, and no prompt assembly occur.

## Records

- **LocalDiagnosticEffectRequest** records the explicit output directory, single artifact name, low-risk local-file effect domain, blocked action labels, source real-effect admission bundle reference when provided, and false network/provider/prompt/subprocess/shell flags.
- **LocalDiagnosticEffectResult** records the artifact path, artifact digest, byte count, and real-effect flags. `real_effect_performed=true`, `local_file_write_performed=true`, and `host_mutation_performed=true` only when the file write succeeds.
- **LocalDiagnosticEffectReceipt** records a real effect receipt for the diagnostic file write only. Fan/PWM, thermal, power, process, service, package, driver, cleanup/delete, network, provider, and prompt flags remain false.
- **LocalDiagnosticPostconditionCheck** reads back only the artifact path written by the pilot, compares digest and byte count, and performs no host mutation.
- **LocalDiagnosticRollbackPlan** and **LocalDiagnosticRollbackReceipt** remain plan/receipt scaffolds during the effect pilot itself. The separate exact-artifact rollback pilot may delete only this recorded artifact when explicitly requested through its API/CLI.
- **LocalDiagnosticProductionAuditReceipt** records production audit evidence for this local diagnostic effect only and performs no additional host mutation.

## CLI

Run the pilot explicitly:

```bash
python scripts/run_local_diagnostic_effect.py --output-dir /tmp/sentientos-local-diagnostic-effect --summary
```

Dry-run validation does not write the artifact:

```bash
python scripts/run_local_diagnostic_effect.py --output-dir /tmp/sentientos-local-diagnostic-effect --dry-run --summary
```

Use `--force` only to overwrite the named target artifact:

```bash
python scripts/run_local_diagnostic_effect.py --output-dir /tmp/sentientos-local-diagnostic-effect --summary --force
```

The default artifact name is `sentientos_local_diagnostic_effect.json`. The CLI refuses root/empty output directories, absolute artifact names, path traversal, artifact names containing path separators, and overwrites without `--force`.

## Reviewer proof bundle posture

The reviewer proof bundle documents this capability in `local_diagnostic_effect_capability.json` and lists the optional command in `proof_commands.json` as `proof_command_not_run`. The reviewer proof bundle does not run this effect by default and remains no-real-effect/no-host-mutation by default.

## Capability registry posture

The capability registry marks `local_diagnostic_effect`, `local_diagnostic_effect_receipt`, `local_diagnostic_postcondition_check`, `local_diagnostic_production_audit_receipt`, and `local_diagnostic_rollback_plan` as implemented for this diagnostic artifact only. `local_diagnostic_exact_rollback`, `local_diagnostic_rollback_postcondition_check`, and `local_diagnostic_rollback_audit_receipt` are implemented as exact-artifact-only surfaces in the separate rollback wing. General cleanup, recursive delete, wildcard delete, unrelated delete, real backends, real backend invocation, fan/PWM, thermal, power, service, and unrelated cleanup actions remain deferred or blocked.

## Implementation links

- Module: `sentientos/local_diagnostic_effect.py`
- CLI: `scripts/run_local_diagnostic_effect.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_local_diagnostic_effect.py`, `tests/test_run_local_diagnostic_effect_script.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

The matching exact-artifact rollback pilot is documented in [Host Local Diagnostic Exact Artifact Rollback Pilot Wing](host_local_diagnostic_exact_rollback_pilot_wing.md); it deletes only the recorded diagnostic artifact when explicitly requested.

Related: [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md) records the diagnostic effect plus exact rollback lifecycle without adding a new host effect.
