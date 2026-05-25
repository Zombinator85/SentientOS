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
Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`.
