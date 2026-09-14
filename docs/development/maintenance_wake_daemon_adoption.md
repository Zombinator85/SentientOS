# Maintenance wake daemon adoption

`sentientos.maintenance_wake_daemon_adoption:v1` is a separate, explicit
operator selection for bounded in-process ownership of the existing recovery-first
maintenance wake cycle. Set `SENTIENTOS_MAINTENANCE_WAKE_ADOPTION_CONFIG` to the
exact adoption document to select it. With no selection, or with `enabled: false`,
`sentientosd` neither discovers a wake profile nor starts a wake owner.

The adoption binds the exact `sentientos.maintenance_wake_cycle_config:v1` path
and digest, a private external state root, separate digest-chained cadence and
owner evidence journals, STOP marker, positive cadence, UTC anchor, initial-run
posture, maximum cycle and wall-clock bounds, and bounded shutdown timeout.
Missed intervals collapse to one due call and completed evidence establishes the
next due instant. Intent is durable before `maintenance_wake_cycle.wake_once`;
an unmatched intent, corrupt journal, configuration drift, lock contention,
STOP, blocked/ambiguous result, or unknown result fails closed without retry.
Each due call receives a freshly sampled timezone-aware UTC evaluation time;
naive clocks are rejected.

The watchdog-only `sentientos.maintenance_scheduler_config:v1` contract is
unchanged. If its daemon adoption and wake adoption are both enabled in one
`sentientosd`, both owners are withheld and read-only health reports the overlap.
Shutdown requests cooperative stop, permits an in-progress bounded wake to
return, joins only for the configured timeout, and reports
`bounded_shutdown_timeout` without killing the thread or changing downstream
locks or journals.

Rendering is available through `scripts/maintenance_loop_activation.py
render-wake-daemon-adoption`; rendering is not adoption, and adoption is not
downstream authority. The first-boot fields `architect_autonomy`,
`codex_interval`, `codex_mode`, and `codex_max_iterations` are outside the closed
schema and cannot select or alter this cadence. Exact base/component staleness
continues to fail closed in this proving phase; future separately reviewed
authority continuity remains possible.

This composition retains the wake cycle's own recovery ordering and component
locks. The daemon does not probe, collect, select, admit, lease, implement,
validate, invoke Git, publish, call providers or networks, inspect credentials,
or install an OS scheduler. Its locking path uses POSIX `fcntl`; native Windows
support is not claimed and no cron, systemd, launchd, Task Scheduler, or service
is installed.
