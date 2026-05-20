# Codex Whole-System Task Template

## Core posture
- Think in systems.
- Land the complete subsystem.
- Fix validation fallout caused by the work.
- Do not stop at local green.
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
Continue remaining feasible checks after failures, classify failures, and fix failures caused by this task.

## Done when
Subsystem landing is complete only when implementation, integration, docs, tests, typing, proof/capability/matrix wiring, and relevant matrix validation are complete.

## Final report format
Include: files changed, validation command outcomes, failure classification, matrix summary/output paths, and unresolved risks.
