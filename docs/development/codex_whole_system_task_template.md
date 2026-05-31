# Codex Whole-System Task Template

## Core posture
- Think in systems.
- Land the complete subsystem.
- Fix validation fallout caused by the work.
- Do not stop at local green.
- After the last task-caused code/doc/test change, run the full relevant validation matrix again before finalization.
- Do not create PR metadata or final "done" reporting before that post-final-change full matrix run passes.
- Returning "If you want, I can run the full matrix now" is non-compliant for system tasks once finalization has started.
- Do not return piddly diffs for subsystem tasks.
- Do not leave proof bundle, capability registry, docs, or matrix integration for follow-up unless explicitly instructed.

## Goal
Describe the subsystem outcome in one paragraph.

## Why this is a system task
Explain why bounded end-to-end landing is required.

## Context
Relevant architecture, constraints, and reviewer-proof surfaces.

## Boundaries
Explicit non-goals and authority/runtime boundaries.

## Inputs
Code/docs/tests/specs consumed.

## Outputs
Expected files, behaviors, and proof artifacts.

## Public API/module
List module or API contract changes.

## CLI
Define operator-facing command surface (if relevant).

## Artifacts
List deterministic outputs/receipts/manifests (if relevant).

## Capability/proof surfaces when relevant
State capability registry and reviewer proof-bundle integration points.

## Matrix integration
State matrix-lane additions/updates and rationale.

## Docs
List docs to update and discoverability links.

## Tests
List unit/integration/docs tests and expected assertions.

## Safety constraints
Re-state no authority widening and no forbidden runtime semantics.

## Compact subsystem profiles
Recurring subsystem families may define compact task profiles so future prompts can reference stable requirements and provide only task-specific deltas. A profile can reduce prompt bulk, but it cannot override `AGENTS.md`, finalizer, PR metadata guard, matrix, supervisor, audit, clean-tree, fixture-root, proof, capability, docs, or authority-boundary requirements. For recurring memory-chain metadata-verification work, use [`codex_memory_chain_task_profile.md`](codex_memory_chain_task_profile.md) unless the prompt explicitly justifies a different profile.

## Validation commands
List full relevant command matrix, not only local targeted tests.

## Failure handling
Required-lane failures are task-owned until proven otherwise.
Continue remaining feasible checks after failures, classify failures, and fix failures caused by this task. Task-caused fallout discovered by the matrix must be fixed in this same task, not deferred to stabilization follow-ups. Do not finalize while required lane failures remain.

## Done when
Subsystem landing is complete only when implementation, integration, docs, tests, typing, proof/capability/matrix wiring, and relevant matrix validation are complete. Non-compliant outcomes include: "feature exists but full matrix not run," creating PR metadata before the post-final-change full matrix run, or proposing follow-up stabilization PRs for task-caused fallout.

## Final report format
Include: files changed, validation command outcomes, failure classification, matrix summary/output paths, and unresolved risks. Final report/PR metadata order is strict: final task-caused change -> full matrix run -> final report and PR metadata.


## Codex Landing Supervisor
Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`. Use two-phase finalization: pre-commit (`--phase pre-commit`) must return `ready_to_commit`; post-commit (`--phase pr-metadata`) must return `ready_for_pr_metadata` before PR metadata.


- For known strict_audits runtime chain drift on `pulse/audit/privileged_audit.runtime.jsonl`, run `python scripts/codex_strict_audit_repair.py diagnose --summary` and then `python scripts/codex_strict_audit_repair.py repair --allow-runtime-chain-reseal --summary`, then rerun strict audits + immutability + matrix/gate/supervisor before finalization.


## Two-phase finalizer commands (required)
Pre-commit finalizer (must return `ready_to_commit` before commit):
```
python scripts/codex_finalize_landing.py finalize \
  --phase pre-commit \
  --title "<COMMIT_TITLE>" \
  --intended-commit-title "<COMMIT_TITLE>" \
  --matrix-json-path /tmp/work_item_review_packet_matrix.json \
  --focused-test-command "<TASK_FOCUSED_TEST_COMMAND>" \
  --targeted-mypy-command "<TASK_TARGETED_MYPY_COMMAND>" \
  --allow-current-tracked-changes \
  --allow-current-task-files \
  --allow-docs-bootstrap \
  --allow-strict-audit-repair \
  --allow-generated-artifact-cleanup \
  --allow-stale-evidence-refresh \
  --summary
```

Post-commit PR-metadata finalizer (must return `ready_for_pr_metadata` before `make_pr` and final report):
```
python scripts/codex_finalize_landing.py finalize \
  --phase pr-metadata \
  --title "<COMMIT_TITLE>" \
  --intended-commit-title "<COMMIT_TITLE>" \
  --matrix-json-path /tmp/work_item_review_packet_matrix.json \
  --focused-test-command "<TASK_FOCUSED_TEST_COMMAND>" \
  --targeted-mypy-command "<TASK_TARGETED_MYPY_COMMAND>" \
  --allow-docs-bootstrap \
  --allow-strict-audit-repair \
  --allow-generated-artifact-cleanup \
  --allow-stale-evidence-refresh \
  --summary
```

No-change path: when no source/doc/test changes were made, do not commit and do not call `make_pr`; report validation-only completion with evidence.

## Final report required fields additions
Include both `pre_commit_finalizer_result` and `post_commit_pr_metadata_finalizer_result`, plus explicit `stale_evidence_refresh_result`, and `pr_metadata_result` showing PR metadata was created only after `ready_for_pr_metadata`.

## Bootstrap and PR metadata guard sequence (required)
1. Run bootstrapper.
2. If bootstrap status is blocked, stop. Do not implement from blocked prompt/scaffold artifacts; report the blocker or ask for a new task.
3. Implement only if bootstrap is ready or ready_with_warnings.
4. Run required validation.
5. Run pre-commit finalizer and require `ready_to_commit`.
6. Commit.
7. Run post-commit/pr-metadata finalizer and require `ready_for_pr_metadata`.
8. Run PR metadata guard and require `pr_metadata_guard_ready`.
9. Only then `make_pr`.

Canonical normal-task guard command:
```bash
python scripts/codex_pr_metadata_guard.py verify \
  --title "<COMMIT_TITLE>" \
  --intended-commit-title "<COMMIT_TITLE>" \
  --pre-commit-finalizer-json "/tmp/<task>_pre_commit.json" \
  --pr-metadata-finalizer-json "/tmp/<task>_pr_metadata.json" \
  --matrix-json-path /tmp/work_item_review_packet_matrix.json \
  --summary
```

Canonical validation-only guard command:
```bash
python scripts/codex_pr_metadata_guard.py verify \
  --title "<COMMIT_TITLE>" \
  --intended-commit-title "<COMMIT_TITLE>" \
  --validation-only \
  --pr-metadata-finalizer-json "/tmp/<task>_pr_metadata.json" \
  --matrix-json-path /tmp/work_item_review_packet_matrix.json \
  --summary
```
