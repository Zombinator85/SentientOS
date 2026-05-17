# Host Embodiment Bounded Built-In Local Effect Runner Pilot Wing

This wing follows the Host Steward / Delegated Runner Boundary and is the first actual delegated runner implementation in SentientOS.

It is intentionally narrow: the runner is a bounded built-in in-process runner that supports only local diagnostic artifact write and exact-artifact rollback, the two already-existing local effect paths:

1. `local_diagnostic_artifact_write` — invokes the existing local diagnostic artifact write path.
2. `local_diagnostic_exact_rollback` — invokes the existing exact-artifact rollback path.

The host steward may model broad top-level authority, but delegated runners do not inherit ambient authority. This built-in runner receives only a narrow, explicit, auditable capability grant for the diagnostic artifact write and the exact-artifact rollback.

## Boundaries

The pilot is in-process only. It does not use subprocess execution, shell execution, network egress, provider invocation, prompt assembly/export, generated-code execution, plugin execution, federation import execution, backend adapter execution, external tool execution, remote execution, or control-plane admission execution.

It is not a general runner framework. Broader delegated runners remain blocked or deferred, including generated-code runners, plugin runners, federation import runners, subprocess runners, shell runners, network runners, provider runners, prompt-assembly runners, hardware-control runners, service-control runners, power-control runners, and cleanup runners.

It does not broaden cleanup, hardware, service, power, thermal, or fan/PWM control. Exact-artifact rollback remains the only delete path and preserves the existing receipt, rollback-plan, path-scope, and digest checks from the local diagnostic exact rollback pilot.

## Records

The wing adds built-in runner policy, declaration, invocation request, invocation result, execution receipt, and block receipt records. All records include deterministic digests and explicit negative flags for subprocess, shell, network, provider, prompt, hardware, service, power, fan/PWM, thermal, general cleanup, recursive delete, and unrelated file deletion.

Successful diagnostic writes include produced record IDs, digests, and paths for effect receipt, postcondition, production audit, and rollback plan records, preserving compatibility with the explicit local effect transaction ledger script. The runner does not automatically build a transaction ledger.

## Reviewer Proof

The reviewer proof bundle documents the built-in runner in `builtin_local_effect_runner_capability.json`, but it does not invoke the runner by default. The proof commands are listed as `proof_command_not_run` for reviewer awareness.

Related docs:

- `docs/architecture/host_steward_delegated_runner_boundary_wing.md`
- `docs/architecture/host_local_diagnostic_effect_pilot_wing.md`
- `docs/architecture/host_local_diagnostic_exact_rollback_pilot_wing.md`
- `docs/architecture/host_local_effect_transaction_ledger_wing.md`
- `docs/architecture/reviewer_first_run_proof_bundle.md`
- `docs/architecture/public_technical_overview.md`
- `docs/architecture/reviewer_release_readiness_index.md`

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.

## Workspace file effect relationship

The [Host Workspace-Scoped File Effect Pilot Wing](host_workspace_file_effect_pilot_wing.md) is available as an explicit API/CLI only in this pass. Built-in runner integration is deferred, so this runner remains limited to local diagnostic artifact write and exact-artifact rollback.
