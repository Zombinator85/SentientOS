# Control-Plane Kernel Adoption Note

## Ownership boundary

The Control-Plane Kernel owns admission decisions for sensitive, phase-aware authority classes that are already integrated at primary boundaries:

- runtime repair actions
- daemon restart actions
- proposal evaluation/adoption and spec-amendment control actions
- federated control intents
- proof-budget-governed admission checks where supplied

## Covered authority classes

Current kernel-governed classes are:

- `repair`
- `daemon_restart`
- `proposal_evaluation`
- `proposal_adoption`
- `federated_control`
- `spec_amendment`

## Intentionally out of scope

The kernel does **not** replace domain-level business logic, execution engines, or non-sensitive observation-only pathways. It gates authority handoff and records decision outcomes; it does not rewrite subsystem internals.

## Lifecycle mediation semantics

- Startup-bound symbols remain startup-guarded by default.
- Runtime mediation is only valid in explicit maintenance phase execution.
- Mediation is symbol-scoped and allowlisted for auditable startup-bound entrypoints.
- Runtime and federation delegates remain independent checks; kernel outcomes include consulted delegate footprints.

## Adding a new sensitive action

1. Create a `ControlActionRequest` with explicit `action_kind`, `actor`, `target_subsystem`, `authority_class`, and `requested_phase`.
2. Route execution through `ControlPlaneKernel.admit(...)` or `admit_and_execute(...)` (do not bypass direct execution).
3. Provide correlation metadata and federation/proof-budget context when applicable.
4. Ensure tests cover allow/deny/defer/quarantine behavior for the new authority path.
