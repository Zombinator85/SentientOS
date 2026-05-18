# Host Workspace Change Set Lifecycle Closure Manifest Wing

This wing follows the [Host Workspace Change Set Execution Verification / Replay Audit Wing](host_workspace_change_set_execution_verification_wing.md). Verification proves what happened. Lifecycle closure seals what the supplied lifecycle evidence means for reviewers and operators.

The implementation is `sentientos/workspace_change_set_lifecycle_closure.py`; the optional CLI is `scripts/build_workspace_change_set_lifecycle_closure.py`.

## Scope

The lifecycle closure wing is metadata-only. It consumes supplied evidence records only:

- workspace change-set manifest, preflight report, rollback plan, and transaction plan metadata;
- execution request, execution result, and execution receipt metadata;
- optional rollback result/receipt, ledger, and execution closure report metadata;
- execution verification request/result metadata.

It emits one deterministic lifecycle closure manifest with IDs, digests, statuses, target ID counts, compact finding codes, blocker codes, contradiction codes, unresolved risk codes, and explicit non-authority boundary flags.

## Lifecycle statuses

The manifest classifies evidence into one compact status:

- `lifecycle_closed_clean`
- `lifecycle_closed_with_partial_state`
- `lifecycle_closed_after_rollback`
- `lifecycle_open`
- `lifecycle_blocked`
- `lifecycle_contradicted`
- `lifecycle_insufficient_evidence`

## Boundaries

The closure manifest is not execution, not rollback, not verification replay, not cleanup, not scheduling, and not a new orchestration layer. It does not read workspace target files, does not recompute target digests from the filesystem, does not invoke workspace file effect helpers, does not invoke execution or rollback helpers, and does not call verification replay helpers. It does not recurse directories, expand wildcards, delete files, call subprocess or shell, open network connections, invoke providers, assemble/export prompts, control services, control power, write fan/PWM or thermal controls, install packages/drivers, execute plugins, execute generated code, or perform federation import execution.

The only optional write is one explicit caller-supplied closure manifest artifact path.

## CLI

The optional CLI builds closure from supplied evidence JSON only:

```bash
python scripts/build_workspace_change_set_lifecycle_closure.py --evidence <workspace_change_set_lifecycle_evidence.json> --summary
```

An explicit output artifact can be requested:

```bash
python scripts/build_workspace_change_set_lifecycle_closure.py --evidence <workspace_change_set_lifecycle_evidence.json> --output <closure_manifest.json>
```

The CLI does not run by default in the reviewer proof bundle. The proof bundle lists the command as `proof_command_not_run` for reviewer awareness.

## Reviewer proof and registry integration

The reviewer proof bundle includes `workspace_change_set_lifecycle_closure_capability.json`. The capability registry marks `workspace_change_set_lifecycle_closure` as implemented with `metadata_lifecycle_closure_only` authority while broader execution, rollback replay, cleanup, scheduling, network, provider, prompt, subprocess, shell, hardware, service, power, fan/PWM, and thermal authority remains blocked or deferred.

## Tests

Focused tests live in:

- `tests/test_workspace_change_set_lifecycle_closure.py`
- `tests/test_build_workspace_change_set_lifecycle_closure_script.py`
- `tests/test_capability_registry.py`
- `tests/test_reviewer_proof_bundle.py`
- `tests/test_reviewer_release_readiness_index.py`
