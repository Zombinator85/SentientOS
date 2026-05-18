# Host Workspace Change Set Execution Verification / Replay Audit Wing

This wing sits after the [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md). It is an independent metadata/read-only verification and replay-audit layer for completed workspace change-set executions.

## What it verifies

The verifier consumes existing workspace change-set manifest, preflight report, rollback plan, transaction plan, execution request, execution result, execution receipt, optional rollback result/receipt, optional execution ledger, and optional closure report evidence. It does not create a new truth source and does not duplicate provenance into a mutable store.

It verifies:

- execution request/result/receipt identity and digest consistency;
- per-target execution evidence and produced record ID/digest consistency;
- planned target order preservation;
- optional rollback order preservation and rollback preimage/absence evidence;
- optional ledger status/order/source consistency;
- optional closure report source and open/failed/skipped target consistency;
- current digest state for explicitly declared manifest targets only;
- visible partial-state classifications for failed, skipped, open, and rolled-back targets;
- unknown or outside-manifest target evidence.

## Verification statuses

The deterministic overall statuses are:

- `verified_clean`
- `verified_with_partial_state`
- `verified_rolled_back`
- `verification_failed`
- `verification_blocked`
- `insufficient_evidence`

Per-target records distinguish postcondition verification, rollback preimage verification, rollback-created-file absence, failed/skipped visibility, failed verification, blocked verification, and insufficient evidence.

## Read-only boundary

The verifier reads only the relative target paths declared in the workspace change-set manifest. It recomputes digests for those declared targets only. It does not recurse directories, expand wildcards, infer undeclared targets, execute target payloads, invoke the change-set execution wing, invoke workspace file effect helpers, invoke rollback helpers, perform cleanup, delete files, call subprocess/shell/network/provider/prompt paths, run external tools, control services, control power, control fan/PWM or thermal state, install packages/drivers, execute plugins/generated code, or perform federation import execution.

The only permitted write is one optional caller-supplied verification/audit artifact path. That artifact records verifier metadata and the verification result; it is not a target mutation, rollback, cleanup, scheduler, or orchestration layer.

## CLI

The optional CLI is `scripts/verify_workspace_change_set_execution.py`. It accepts a JSON evidence bundle containing the preflight/planning and execution evidence and prints either JSON or a compact summary:

```bash
python scripts/verify_workspace_change_set_execution.py --evidence <workspace_change_set_execution_evidence.json> --summary
```

The CLI is verification-only. It does not build fresh preflight, does not execute a transaction, does not rollback, and does not run by default in the reviewer proof bundle.

## Reviewer proof posture

The reviewer proof bundle documents `workspace_change_set_execution_verification_capability.json` but does not run verification by default. The listed proof command is `proof_command_not_run` for reviewers who explicitly want to replay-audit completed evidence.
