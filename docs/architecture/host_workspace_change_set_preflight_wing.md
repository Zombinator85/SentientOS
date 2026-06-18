# Host Workspace Change Set Preflight / Planning Wing

This wing follows the [Host Workspace File Transaction Orchestrator Wing](host_workspace_file_transaction_orchestrator_wing.md) and prepares the next step toward future bounded multi-target workspace transactions. It records a workspace change set manifest, validates explicit target declarations, captures read-only target preflight metadata, and builds rollback and transaction planning records.

It prepares multi-target workspace changes but does not execute them. Future workspace change-set execution remains deferred.

## Implemented records

- Workspace Change Set Manifest — a bounded metadata manifest of explicit relative target paths.
- Workspace Change Target Declaration — an explicit target path, operation, payload declaration, and scope labels.
- Workspace Change Target Preflight — read-only metadata and optional digest capture for exactly the declared target.
- Workspace Change Set Preflight Report — pass/block summary for the declared targets.
- Workspace Change Set Rollback Plan — metadata-only rollback strategy entries; rollback is not performed.
- Workspace Change Set Transaction Plan — metadata-only planned ordering and strategy for a future executor.
- Workspace Change Set Block Receipt — metadata-only block reasons when preflight cannot safely proceed.

## Bounds and checks

The default policy allows at most eight explicit targets, 65,536 payload bytes per target, and 262,144 total payload bytes. It rejects empty or root workspace roots, duplicate normalized target paths, absolute target paths, path traversal, wildcard-like target names, targets outside the workspace, symlink targets, directory targets, missing parent directories, missing update/replace targets, and create targets that already exist when replacement is disallowed.

The wing reads only explicitly declared target metadata/digests. It is not general filesystem access and it does not scan sibling files or undeclared targets.

## Non-effects

This is a preflight/planning wing only:

- no target files are written;
- no target payloads are applied;
- no rollback occurs;
- no built-in runner or transaction orchestrator is invoked;
- no workspace file effect write or rollback path is called;
- no cleanup occurs;
- no recursive delete, wildcard delete, or unrelated file delete occurs;
- no subprocess, shell, network, provider, prompt, OS backend, remote execution, federation import execution, generated-code execution, plugin execution, or control-plane execution occurs;
- no hardware, service, power, fan/PWM, or thermal control occurs.

The optional CLI can write one explicit local preflight/plan JSON artifact to a caller-supplied output path, but that artifact is not a target payload write and does not execute a change set.

## Reviewer proof posture

The reviewer proof bundle documents `workspace_change_set_preflight_capability.json` but does not run change-set preflight by default. The proof command is listed as `proof_command_not_run` for reviewers who explicitly want to inspect the preflight/planning CLI. This optional command can prove that the preflight/planning wing builds bounded manifest, preflight report, rollback-plan, and transaction-plan records for the declared targets; it cannot prove that a workspace change was applied, that rollback executed, or that any runner/orchestrator was invoked.

Focused regression coverage for the preceding admission handoff lives in `tests/test_workspace_change_set_admission.py`. Those tests prove admission remains metadata-only, omits payload bodies, does not read target files, does not check target existence, does not compute filesystem digests, and does not invoke preflight helpers before declaring that preflight may be attempted next.

## Future work remains deferred

Workspace change-set transaction execution now follows in the bounded execution pilot wing; multi-file runner actions and bulk cleanup rollback remain deferred behind new authority, safety, audit, rollback, and operator approval gates.

## Next wing

The bounded successor is [Host Workspace Change Set Transaction Execution Pilot Wing](host_workspace_change_set_execution_wing.md), which consumes passed preflight and ready transaction plans before delegating each explicit target to the single-target workspace file helper.
