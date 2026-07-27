# Whole-System Codex Task Template

Use this compact issue structure. Stable repository law is inherited from root [`AGENTS.md`](../../AGENTS.md); validation policy comes from [`codex_validation_and_landing_contract.md`](codex_validation_and_landing_contract.md), and executable commands come only from [`codex_finalize_landing.md`](codex_finalize_landing.md).

## Objective
State the complete bounded subsystem outcome and operator value.

## Verified current gap
Cite inspected code, docs, tests, and the observable missing behavior. Bootstrap first and stop if blocked.

## Boundaries
Name allowed surfaces and explicit non-goals, especially provider, network, host-effect, consent, policy, federation, prompt-export, and runtime-authority limits.

## Observable acceptance proof
List exact successful behavior, denial/failure cases, deterministic artifacts, public/CLI surfaces when applicable, and exact pytest node IDs in the task acceptance manifest. Behavior-adding tasks require a successful-path node.

## Relevant surfaces
List implementation, integration, docs, typing, capability/proof, reviewer/index, and matrix surfaces that genuinely apply. Do not manufacture a runtime capability for developer workflow work.

## Task-specific validation
List only focused tests, targeted mypy scope, relevant matrix lane, and additional task-specific checks. Inherit bootstrap, baseline, docs/prompt checks, audits, clean-tree rules, two-phase finalizer, guard, body binding, and `make_pr` procedure by reference; do not duplicate their command blocks.

## Done when
The objective, integration, documentation, exact-node behavioral proof, required matrix, repair loop, and canonical landing contract all pass after the last task-caused change. Do not defer task-caused stabilization.
