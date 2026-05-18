# Host Workspace-Scoped File Effect Pilot Wing

The Host Workspace-Scoped File Effect Pilot Wing follows the bounded built-in runner transaction orchestrator. It is the first useful workspace-scoped file update pilot after the diagnostic artifact write/exact-rollback chain.

## Scope

This wing creates or updates exactly one explicit file inside an explicit caller-supplied workspace root. The caller supplies both:

- `workspace_root`: the workspace boundary.
- `relative_target_path`: the single relative target path.

The target path is normalized and scope-checked. Absolute targets, path traversal, symlink targets, directory targets, targets outside the workspace root, root workspace claims, and missing parent directories are refused.

## Records

The API in `sentientos/workspace_file_effect.py` builds:

- request records for the single workspace-scoped file effect;
- preimage records before replacement;
- effect results and receipts that distinguish new-file creation from replacement;
- exact-target postcondition checks;
- rollback plans and rollback receipts;
- rollback postcondition checks;
- production audit receipts for this workspace-file effect only.

Preimage capture is exact-target only. For replacements, the prior bytes are captured in-record as deterministic base64 so exact rollback can restore the preimage. For creations, rollback removes only the exact created file after checking the expected current digest.

## Rollback boundary

Rollback is explicit and exact-target only:

- created-file rollback removes only the exact created target;
- replacement rollback restores only the exact captured preimage;
- rollback refuses digest mismatch;
- rollback refuses symlink, directory, and out-of-scope targets;
- rollback does not delete siblings or directories.

No directory cleanup, recursive deletion, wildcard deletion, or unrelated file deletion is implemented.

## Non-authority statements

This is not general filesystem access. It is not cleanup. It is not recursive, wildcard, broad, or unrelated deletion. It does not use subprocess execution, shell execution, network egress, provider invocation, prompt assembly/export, federation transport/sync/adoption, remote execution, OS backend invocation, or `control_plane_kernel.admit_and_execute`.

This wing does not touch hardware, services, power profiles, fan/PWM control, thermal actuation, process killing, package installation, or driver installation. Those surfaces remain blocked/deferred.

## CLI

Explicit command/API only:

```bash
python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload "hello" --summary
```

Optional exact rollback demonstration:

```bash
python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload "hello" --rollback --summary
```

Dry-run validation writes nothing:

```bash
python scripts/run_workspace_file_effect.py --workspace-root /tmp/sentientos-workspace-file-effect --target demo.txt --payload "hello" --dry-run --summary
```

## Reviewer proof bundle and runner status

The reviewer proof bundle includes `workspace_file_effect_capability.json` and lists the workspace file commands as `proof_command_not_run`. The proof bundle does not run this effect by default.

Built-in runner integration is deferred in this pass. The existing bounded runner transaction orchestrator still supports only the diagnostic write and exact diagnostic rollback actions.

See also: [Host Workspace File Runner / Transaction Integration Wing](host_workspace_file_runner_transaction_wing.md).

- Workspace file transaction orchestrator: see [Host Workspace File Transaction Orchestrator Wing](host_workspace_file_transaction_orchestrator_wing.md) for implemented single-target workspace update/rollback/ledger modes; the previous orchestration deferral is removed without adding general filesystem, cleanup, subprocess, shell, network, provider, prompt, or hardware/service/power/fan/thermal authority.

## Next workspace planning wing

See [`Host Workspace Change Set Preflight / Planning Wing`](host_workspace_change_set_preflight_wing.md) (`docs/architecture/host_workspace_change_set_preflight_wing.md`) for the metadata-only layer that prepares bounded multi-target workspace changes but does not execute them, reads only explicitly declared target metadata/digests, performs no target writes, performs no rollback, invokes no runner/orchestrator, and leaves future change-set execution deferred.

## Successor link

The file effect pilot remains the single-target machinery used by [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md).
