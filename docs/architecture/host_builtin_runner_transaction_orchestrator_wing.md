# Host Built-In Runner Transaction Orchestrator Wing

The Host Built-In Runner Transaction Orchestrator Wing follows the Bounded Built-In Local Effect Runner Pilot. It proves that the already-bounded local diagnostic write, exact-artifact rollback, and local effect transaction ledger can be composed into one explicit, auditable transaction lifecycle without expanding runner authority.

## Scope

This wing orchestrates only the existing in-process bounded built-in runner actions:

- `local_diagnostic_artifact_write`
- `local_diagnostic_exact_rollback`

It supports four transaction modes:

- `diagnostic_write_only`
- `diagnostic_write_with_rollback`
- `diagnostic_write_with_ledger`
- `diagnostic_write_rollback_with_ledger`

Ledger construction is explicit. The orchestrator can build the local effect transaction ledger around produced diagnostic and rollback records, and it can write one caller-supplied ledger artifact path only when a ledger mode and `--ledger-output` are supplied.

## Non-goals and blocked authority

This is not a general runner framework. It is not a new host effect class, subprocesses, shell execution, network egress, provider invocation, prompt assembly/export, generated-code execution, plugin execution, federation import execution, external tool execution, service control, power control, hardware control, fan/PWM control, thermal actuation, package/driver installation, general cleanup, recursive delete, unrelated file deletion, remote execution, or uncontrolled runtime authority expansion.

The orchestrator preserves the built-in runner's safety checks and the exact-artifact-only rollback checks. Broader runner orchestration remains blocked/deferred.

## Transaction records

The module defines bounded policy, plan, execution request, result, receipt, closure report, and validation records. Plans and requests are metadata until explicit execution. Dry-run mode validates and creates plan/request/result/receipt/closure metadata without writing, rolling back, building a ledger artifact, invoking subprocesses, opening network egress, invoking providers, or assembling prompts.

## Partial state visibility

If diagnostic write succeeds and rollback fails, the result and closure report keep the transaction open with rollback failure/pending evidence. If diagnostic write succeeds and ledger construction fails, the result records ledger failure/pending evidence. Partial state is never hidden.

## Reviewer proof bundle

The reviewer proof bundle documents this capability in `builtin_runner_transaction_orchestrator_capability.json` and lists the optional proof command as `not_run`. The default proof bundle does not invoke the orchestrator, runner, effect, rollback, or ledger by default.

## Proof links

- Module: `sentientos/builtin_runner_transaction_orchestrator.py`
- CLI: `scripts/run_builtin_runner_transaction.py`
- Tests: `tests/test_builtin_runner_transaction_orchestrator.py`, `tests/test_run_builtin_runner_transaction_script.py`
- Preceded by: [Bounded Built-In Local Effect Runner Pilot](host_builtin_local_effect_runner_pilot_wing.md)
- Ledger: [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md)
- Rollback: [Host Local Diagnostic Exact Rollback Pilot Wing](host_local_diagnostic_exact_rollback_pilot_wing.md)
