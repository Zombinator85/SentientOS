# Host Workspace File Transaction Orchestrator Wing

This wing follows the workspace file runner/transaction integration and removes
the prior `workspace_file_transaction_orchestration` deferral. The existing
bounded runner transaction orchestrator now supports one-command workspace file
transactions for exactly one explicit relative target inside exactly one
caller-supplied workspace root.

Implemented modes:

- `workspace_file_update_only`
- `workspace_file_update_with_rollback`
- `workspace_file_update_with_ledger`
- `workspace_file_update_rollback_with_ledger`

The orchestrator only delegates to existing built-in runner actions:

- `workspace_scoped_file_update`
- `workspace_scoped_file_exact_rollback`

Ledger integration uses only the existing workspace file transaction ledger
helpers. If a caller supplies `--ledger-output` in a ledger mode, the CLI writes
one explicit workspace transaction ledger artifact to that caller-supplied path.
The reviewer proof bundle documents this command but does not run it by default.

This is not general filesystem access. It is not cleanup. It is not recursive,
wildcard, or unrelated deletion. Workspace rollback remains exact-target only:
it removes only the newly-created target proven by receipt and rollback plan, or
restores the exact captured preimage for a replaced target. Sibling files and
directories are outside the rollback authority.

The orchestrator does not use subprocess, shell, network, provider, prompt, or
control-plane execution. It does not touch hardware, services, power, fan/PWM,
or thermal controls.

If update succeeds but rollback or ledger construction fails, the transaction
result and receipt remain incomplete and preserve the produced record IDs,
digests, paths, and warnings so partial state is visible to reviewers.
