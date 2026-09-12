# Maintenance Loop Watchdog

The maintenance-loop watchdog is external developer-workflow machinery. It is a
deterministic coordinator, not a daemon: each tick observes external custody,
selects exactly one top-level transition, delegates that transition to an existing
canonical component, records the result, and stops. `run-bounded` repeats ticks only
until a configured action/time bound or a terminal idle, waiting, paused, or blocked
result. It never installs or supplies a scheduler and is not integrated into
`sentientosd`.

Commit `83cca3e` introduced the deterministic watchdog scaffold, `cc7a9da`
added canonical scanning and selection, admission, and landing dispatch, and
`5e16605` added process-real implementation continuation. This continuation adds
validation/correction continuation and the first genuine production-CLI closed-loop
proof. The
production coordinator now discovers the canonical task journals and immutable component
artifacts directly and uses a closed internal dispatch table; legacy synthetic
state summaries and caller-supplied transition handlers have no execution
authority.

The watchdog now connects admitted work to process-real local-Codex implementation:
it seals deterministic instruction and request custody, starts the existing
implementation-agent session, and delegates execution and same-thread recovery to
the local-Codex foreman until `implementation_ready_for_validation`. It now binds
that exact result, lease, attempt, session, thread, worktree, change manifest, and
validation policy to the existing validation controller. The controller retains
planning, execution, same-thread correction, remeasurement, revalidation, recovery,
and immutable custody. Exact passing evidence then reaches the existing commit and the configured landing
mode: remote fast-forward, pull request, or offline local base-ref absorption. Verified
landing evidence then permits base-cursor advancement, closure, and the idle path.
The production-CLI fake closed-loop proof passes, so the bounded core maintenance
loop is complete.

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

Remote `fast_forward_base_ref` permits closure and base-cursor advancement only
after an exact remote observation equals the task commit. PR creation is not merge
evidence: pull-request work remains waiting until a later remote observation proves
the task commit is an ancestor of the tracked base. These remote modes retain their
configured remote-observation and ancestry semantics.

For `local_fast_forward_base_ref`, closure instead requires exact equality of the
configured local tracked ref to the absorbed commit. A local-only activation requires
`repository_commit` and `local_repository_base_advance`, rejects remote publication
authorities, and can operate without a configured Git remote or PR publication client.
The landing controller performs the exact local compare-and-swap and checkout
synchronization; the watchdog does not weaken its clean-tree, identity, recovery, or
no-network guarantees.

Only explicitly retryable landing failures may be retried after configured deterministic
backoff. Authentication, integrity, and remote/local conflict failures block without a
hot loop. Local absorption changes the canonical checkout on disk but does not restart a
running SentientOS process, load the new code into that process, or adopt runtime
capability.

The coordinator never duplicates implementation, validation, Git, or publication
logic, merges, force-pushes, waits for hosted checks, reads credential contents, or
relays operator messages between stages. Those effects remain with the established
candidate, journal, lease, foreman, validation, commit, and publication components.
Unattended repetition still requires external configuration, an explicit standing
grant, authenticated tools appropriate to the selected implementation/validation/landing
path, a candidate inbox, external state/workspace/scratch custody roots, and an external
scheduler invocation. Remote modes require their remote/publication authority and tools;
a local-only mode does not require remote authority, a configured Git remote, or a PR
client. Neither mode makes the watchdog a scheduler or integrates it into `sentientosd`.

## CLI

`scripts/maintenance_loop_watchdog.py` provides `doctor`, `scan`, `decide`, `tick`,
`run-bounded`, `recover`, `pause`, `resume`, `inspect`, `inspect-control`, and
`inspect-base-cursor`. Every command requires an explicit configuration; commands
whose result depends on time also require an explicit evaluation time.
