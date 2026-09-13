# Maintenance wake-daemon adoption authority eligibility

`maintenance_wake_daemon_adoption` makes a future implementation task eligible for
bootstrap planning under one exact authority definition. This is eligibility metadata,
not a grant, lease, runtime admission, or effect.

The eligible definition binds the `maintenance` subsystem to the
`deterministic_maintenance_wake_daemon_controller` principal and only the exact effects
needed to read explicit operator adoption and wake configuration, invoke one bounded
maintenance wake-cycle boundary, own a bounded daemon lifecycle, write narrow evidence,
and project read-only health.

This does **not** mean that `sentientosd` can currently run the maintenance wake cycle on
a cadence. Wake cadence, daemon lifecycle and shutdown, `sentientosd` integration,
`maintenance_wake_cycle.wake_once` invocation, and runtime evidence remain deferred to a
separately bootstrapped implementation task.

The future owner may invoke only the existing recovery-first maintenance wake-cycle
boundary. The health probe, governed improvement signal source, candidate collector,
autonomy cycle, selector, admission, standing grant, lease, implementation, validation,
Git, publication, and runtime adoption retain their existing separate authority and
custody. Eligibility does not permit automatic renewal, self-granting, arbitrary
commands or scheduler targets, credentials, provider/network access, or OS service
installation.

## Preset and subsystem routing

`preset_id` selects scaffold defaults and is verified when explicitly supplied.
`subsystem_kind` classifies the task. For compatibility, an omitted preset may be
verified when the subsystem is itself a registered preset ID; a specialized subsystem
such as `maintenance` is not treated as an unknown preset and does not select one.
An explicitly supplied unknown preset remains an error reported by the preset verifier.
