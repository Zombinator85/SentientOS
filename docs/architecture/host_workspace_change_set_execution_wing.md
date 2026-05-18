# Host Workspace Change Set Transaction Execution Pilot Wing

This wing follows the [Host Workspace Change Set Preflight / Planning Wing](host_workspace_change_set_preflight_wing.md). It is the first bounded multi-target workspace execution layer in SentientOS: preflight made multi-target reasoning possible, and this wing makes bounded multi-target execution possible only after a passed preflight report and a ready transaction plan.

## What it executes

The execution wing consumes the explicit Workspace Change Set Manifest, Workspace Change Set Preflight Report, Workspace Change Set Rollback Plan, and Workspace Change Set Transaction Plan produced by the preflight/planning wing. It refuses execution unless preflight is passed or passed-with-warnings and the transaction plan is ready or ready-with-warnings.

Targets execute strictly in planned order. Each target must already be declared in the manifest as an explicit relative path inside one explicit workspace root. The wing rechecks preflight digest posture before writing so drift since preflight blocks execution.

## How it executes

The wing does not introduce a general filesystem API. For each target it delegates to the existing single-target workspace file effect helper in `sentientos/workspace_file_effect.py`. Per-target execution records capture the workspace effect receipt, postcondition check, exact-target rollback plan, production audit receipt, before/after digests, and target status.

## Rollback and partial-state visibility

Rollback is optional and exact-target-only. Rollback runs in reverse execution order and delegates to the existing workspace file exact rollback helper. Rollback can occur after a successful execution when explicitly requested, or after a later target failure when rollback-on-failure is enabled.

Partial state is never hidden. Applied, failed, skipped, and rolled-back target identifiers are recorded in the execution result, execution receipt, rollback result, transaction ledger, and closure report.

## Ledger and closure report

The transaction ledger and closure report are metadata-only. They perform no additional target effects. A caller may request one explicit ledger artifact at a safe caller-supplied path inside the workspace root after execution and rollback state are known.

## Non-authorities

This wing is not general filesystem access. It is not cleanup. It is not recursive deletion, wildcard deletion, unrelated file deletion, service control, power control, hardware control, fan/PWM control, thermal actuation, package/driver installation, subprocess execution, shell execution, generated-code execution, plugin execution, federation import execution, external tool execution, network egress, provider invocation, prompt assembly/export, remote execution, or uncontrolled runtime authority expansion.

## Reviewer proof posture

The reviewer proof bundle documents `workspace_change_set_execution_capability.json` but does not run workspace change-set execution by default. The listed proof command is `proof_command_not_run` so reviewers can explicitly invoke the bounded pilot if desired.
