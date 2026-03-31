# Codex startup guard lifecycle semantics

This note defines the post-kernel-hardening behavior of `sentientos.codex_startup_guard`.

## Authority model

- **Startup authority**: granted only inside `codex_startup_phase()` before finalization.
- **Finalized state**: once startup exits, startup authority is sealed and cannot be re-entered.
- **Mediated authority**: granted only by `codex_runtime_mediation(symbol)` for allowlisted startup-gated symbols; this is valid for runtime/maintenance execution without making startup active.

## Process model

- Guard state is process-bound via owner PID tracking.
- Child/forked processes are forced into `active=False, finalized=True` unless startup env markers are explicitly cleared before process creation.
- Runtime mediation stacks are cleared on PID transitions and in fork children to prevent inherited mediation authority.

## Kernel interaction

- `ControlPlaneKernel.admit_and_execute(..., startup_symbol=...)` uses runtime mediation only in maintenance phase.
- Startup authority and mediated authority remain distinct in both state (`codex_startup_state`) and behavior (`enforce_codex_startup`).
- Finalized startup does not permit raw startup re-entry but does permit explicitly mediated maintenance execution.
