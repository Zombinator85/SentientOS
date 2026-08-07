# Bounded maintenance autonomy cycle

The maintenance autonomy cycle is an **external bounded coordinator**, not a new
authority system. It calls the governed candidate collector and production
watchdog library APIs in recovery-first order and inherits their validation,
selection, admission, implementation, validation, Git, publication, cursor, and
closure rules by reference.

Each invocation holds an outer cycle lock, checks the shared `STOP` marker before
each effect stage, continues an active task before considering new work, consumes
an existing inbox candidate before collecting, and otherwise collects at most one
candidate and invokes the watchdog at most once. Component locks remain internally
owned, so the coordinator does not reverse their lock order. A paused, waiting,
blocked, ambiguous, or integrity-failed component result is never called complete.

Every completed invocation appends a canonical, digest-chained receipt in private
external custody. The receipt binds configuration and component-result identities,
stage order, STOP observations, effect counts, and terminal status without copying
credentials, transcripts, validator output, environment values, or implementation
instructions. On restart, canonical inbox and watchdog custody is inspected first:
collection is not repeated after a collected candidate, and completed downstream
effects are not reconstructed or repeated. Receipt chain disagreement fails closed.

## Manual and scheduled invocation

Use `doctor`, then invoke `cycle-once` with the explicit configuration and
evaluation time. `inspect`, `inspect-receipts`, and `print-run-command` are
read-only; the latter returns an argv array and never shell interpolation.

The runner does not grant authority. Collector intake remains proposal-only, and
the watchdog retains admission and every downstream authority. SentientOS does
not install cron, systemd, launchd, Task Scheduler, a service, timer, daemon, or
any other scheduler. Live operation still requires authenticated tools, a valid
standing grant, external custody, source production, and an operator-controlled
external scheduler.
