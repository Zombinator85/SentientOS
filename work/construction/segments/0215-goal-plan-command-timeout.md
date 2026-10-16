# Sequence 215 — Bound plan command runtime

The shell-free allowlist still had no execution deadline. A hung diagnostic or verification process could hold a work-plan run indefinitely. Allowlisted subprocesses now have a five-minute timeout; timeout raises a failed task with reason `command_timeout`, no artifact claim, and no shell execution.

Validation: 11 goal executor planning, execution, and goal-state tests passed. Changed modules compiled and diff check passed. Existing mode/quarantine destructive gates remain in place.

Next: harden the persisted work-plan parsing boundary. Current parsing coerces fields and skips malformed task rows; inspect persisted compatibility, then make malformed or identity-inconsistent plans fail closed before any task can execute.
