# Host Workspace Change Set Lifecycle Orchestration Wing

The Host Workspace Change Set Lifecycle Orchestration Wing is a bounded coordinator for the existing workspace change-set wings. It composes the already-audited flow:

1. admission,
2. preflight / transaction planning,
3. optional bounded execution,
4. optional execution verification / replay audit,
5. optional lifecycle closure.

It is not a new file-effect primitive, executor, verifier, closure system, cleanup path, scheduler, or autonomy loop. Target mutation can occur only when an execution mode is requested and only through `sentientos/workspace_change_set_execution.py`.

## API and CLI

- Module: `sentientos/workspace_change_set_lifecycle_orchestrator.py`
- CLI: `scripts/run_workspace_change_set_lifecycle.py`
- Example:

```bash
python scripts/run_workspace_change_set_lifecycle.py --proposal proposal.json --workspace-root /tmp/sentientos-workspace-change-set --mode admit_preflight_execute_verify_close --summary
```

## Supported modes

- `admit_only`
- `admit_and_preflight`
- `admit_preflight_execute`
- `admit_preflight_execute_verify`
- `admit_preflight_execute_verify_close`
- `dry_run_full_lifecycle`

`dry_run_full_lifecycle` runs admission and preflight/planning only, then emits a lifecycle summary. It does not execute targets, verify target state, or build closure requiring execution evidence.

## Stage gating

The orchestrator fails closed with deterministic stop reasons. Admission must permit preflight, preflight must pass and produce a ready transaction plan before execution, execution evidence must exist before verification, and verification evidence must exist before lifecycle closure.

Representative stop reasons include `admission_blocked`, `admission_contradicted`, `admission_insufficient_metadata`, `preflight_blocked`, `transaction_plan_not_ready`, `execution_blocked`, `execution_failed`, `verification_failed`, `closure_contradicted`, `insufficient_evidence_for_requested_stage`, and `lifecycle_completed_for_requested_mode`.

## Artifact behavior

The orchestrator may write only caller-supplied stage artifacts and a caller-supplied final orchestration artifact. The final result stores compact IDs, statuses, counts, digests, and artifact paths; it does not duplicate target payloads, preimage bodies, prompt text, secrets, runtime handles, or filesystem content.

## Non-authority boundaries

The orchestrator records explicit non-authority boundaries: no new file-effect primitive, no direct target file reads, no target digest recomputation in the orchestrator, no cleanup/delete/recursion/wildcards, no external-tool/provider paths, execution only through the existing change-set execution wing, verification only through the existing verification wing, and closure only through the existing lifecycle closure wing.

## Reviewer proof

The reviewer proof bundle documents `workspace_change_set_lifecycle_orchestration_capability.json` and lists the CLI as an optional `proof_command_not_run`. The proof bundle does not run full lifecycle orchestration by default.
