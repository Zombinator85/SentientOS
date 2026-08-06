# Maintenance Loop Watchdog

The maintenance-loop watchdog is external developer-workflow machinery. It is a
deterministic coordinator, not a daemon: each tick observes external custody,
selects exactly one top-level transition, delegates that transition to an existing
canonical component, records the result, and stops. `run-bounded` repeats ticks only
until a configured action/time bound or a terminal idle, waiting, paused, or blocked
result. It never installs or supplies a scheduler and is not integrated into
`sentientosd`.

## Safety and recovery contract

Decision order is pause/STOP, integrity failure, active-task ambiguity, exact
recovery, live-process observation, closure, publication, commit/enqueue,
validation, implementation, admission, selection, then idle. Recovery therefore
precedes every new effect. A global process lock serializes ticks, and the external
STOP marker is rechecked immediately before dispatch. Pause and resume are
append-only digest-chained control events.

Configuration names the repository, external state/workspace/scratch/candidate
roots, standing operator grant, selector/foreman/validation/landing policies,
single-active-task limit, action/time bounds, publication backoff, exact base SHA,
and tracked base ref. Custody roots must exist outside the repository and `.git`
and must not be symlinks. The standing grant is input authority; the watchdog cannot
create or expand it.

Fast-forward publication permits closure and base-cursor advancement only after an
exact remote observation equals the task commit. PR creation is not merge evidence:
PR-mode work remains waiting until a later remote observation proves the task commit
is an ancestor of the tracked base. Only explicitly retryable publication failures
may be retried after configured deterministic backoff. Authentication, integrity,
and remote-conflict failures block without a hot loop.

The coordinator never implements changes, validates them, performs Git plumbing,
merges, force-pushes, waits for hosted checks, reads credential contents, or relays
operator messages between stages. Those effects remain with the established
candidate, journal, lease, foreman, validation, commit, and publication components.

## CLI

`scripts/maintenance_loop_watchdog.py` provides `doctor`, `scan`, `decide`, `tick`,
`run-bounded`, `recover`, `pause`, `resume`, `inspect`, `inspect-control`, and
`inspect-base-cursor`. Every command requires an explicit configuration; commands
whose result depends on time also require an explicit evaluation time.
