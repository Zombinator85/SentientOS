# Host Embodiment Workspace File Runner / Transaction Integration Wing

This wing follows the [Workspace-Scoped File Update Pilot](host_workspace_file_effect_pilot_wing.md) and integrates that narrow pilot into the bounded built-in runner surface.

## Implemented surface

- `workspace_scoped_file_update` invokes the existing `sentientos.workspace_file_effect` create/update path in-process.
- `workspace_scoped_file_exact_rollback` invokes the existing exact rollback path in-process.
- Each action is for one explicit relative target inside one explicit workspace root.
- Existing workspace checks remain the authority boundary: path normalization, scope containment, preimage capture, digest verification, symlink rejection, directory rejection, postcondition checks, rollback plan checks, and production audit records.
- `sentientos.workspace_file_transaction_ledger` builds a metadata-only digest-chained ledger and lifecycle report from explicit workspace file records.
- `scripts/build_workspace_file_transaction_ledger.py` can optionally write one explicit caller-supplied ledger artifact.

## Non-goals and blocked authority

This is not general filesystem access. It is not cleanup. It is not recursive deletion, wildcard deletion, unrelated deletion, directory mutation, service control, power control, hardware control, fan/PWM control, thermal actuation, package or driver installation, subprocess execution, shell execution, generated-code execution, plugin execution, federation import execution, external tool execution, network egress, provider invocation, prompt assembly/export, remote execution, or uncontrolled runtime authority expansion.

The new runner code does not introduce its own broad file operations. Workspace file rollback remains delegated to the existing exact-target rollback function.

## Reviewer proof posture

The reviewer proof bundle documents this capability with `workspace_file_runner_transaction_capability.json` but does not run workspace update, rollback, runner actions, or ledger building by default. Proof commands are listed as `proof_command_not_run` for reviewer awareness.

## Transaction orchestrator status

Built-in transaction orchestrator integration for workspace file modes is now implemented by the follow-up workspace transaction orchestrator wing. The runner integration and metadata-only workspace transaction ledger remain the bounded substrate; orchestration was added without broadening the diagnostic modes or granting general filesystem authority.

- Workspace file transaction orchestrator: see [Host Workspace File Transaction Orchestrator Wing](host_workspace_file_transaction_orchestrator_wing.md) for implemented single-target workspace update/rollback/ledger modes; the previous orchestration deferral is removed without adding general filesystem, cleanup, subprocess, shell, network, provider, prompt, or hardware/service/power/fan/thermal authority.

## Next workspace planning wing

See [`Host Workspace Change Set Preflight / Planning Wing`](host_workspace_change_set_preflight_wing.md) (`docs/architecture/host_workspace_change_set_preflight_wing.md`) for the metadata-only layer that prepares bounded multi-target workspace changes but does not execute them, reads only explicitly declared target metadata/digests, performs no target writes, performs no rollback, invokes no runner/orchestrator, and leaves future change-set execution deferred.

## Successor link

The runner transaction wing remains single-target; bounded multi-target workspace execution is documented in [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md).
