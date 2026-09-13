# Bounded Maintenance Cadence Runner

SentientOS provides an explicitly operator-selected bounded cadence runner around one
already activated watchdog configuration. Schema
`sentientos.maintenance_scheduler_config:v1` binds the exact config path and digest,
external state root, interval, initial posture, UTC anchor, cycle/time bounds,
failure threshold, stop marker, journal path, and scheduler digest.

`run-once` is non-sleeping. `run-bounded` uses monotonic time for live waiting and
bounds; UTC evidence reconstructs restarts. Scheduler and watchdog bounds remain
independent and there is no forever mode. After downtime, one due invocation runs;
missed intervals collapse and the next due time is the first cadence instant after
actual invocation. There is no catch-up storm or rollback-driven duplicate.

An external `scheduler.lock` serializes due decisions; contention does not advance
the cursor. Digest-chained `sentientos.maintenance_scheduler_event:v1` records bind
the configs, ordinal, times, predecessor, observed watchdog result, duration,
disposition, failure count, and next due time. Corruption fails closed. A durable
invocation intent precedes the watchdog call; an unmatched intent after a crash
blocks rather than risking duplication. Before that intent a restart may retry, and
a completed receipt reconstructs the next cycle.

Every invocation reloads and validates the exact watchdog config. Drift blocks.
Scheduler STOP prevents new calls but never kills a running watchdog. Watchdog
`paused` stops scheduling. `idle`, `waiting`, `completed`, and `time_limit` advance
one cadence; `blocked` increments failures and the threshold terminates execution.

Scheduler invocation is not an authority grant. It does not generate candidates,
issue leases, implement, validate, mutate Git, publish, inspect credentials, invoke
providers/networks, or restart/adopt repository changes. `sentientosd` starts the
bounded maintenance scheduler only when an operator explicitly configures adoption
of one exact scheduler profile. SentientOS installs no cron, systemd, launchd, or
Task Scheduler. First-boot `architect_autonomy`,
`codex_interval`, `codex_mode`, and `codex_max_iterations` are deliberately not
scheduler configuration or authority.

The CLI exposes deterministic JSON `doctor`, `run-once`, `run-bounded`, and
`inspect`. Activation tooling separately renders/doctors the profile and prints its
argv; none of those steps starts it.

## Explicit `sentientosd` adoption

The operator separately renders `sentientos.maintenance_scheduler_daemon_adoption:v1`
and supplies its path through
`SENTIENTOS_MAINTENANCE_SCHEDULER_ADOPTION_CONFIG`. The record contains an explicit
enabled posture, exact scheduler path and digest, expected scheduler schema, external
daemon evidence path, bounded shutdown timeout, and positive re-entry delay. Rendering
a scheduler profile does not render or enable adoption, and no profile is discovered.

A dedicated daemon-owned thread revalidates the exact profile and its watchdog binding
before every bounded lifetime. Ordinary cycle/time bounds may re-enter only after the
configured delay. STOP, pause, failure threshold, lock contention, config drift, and
ambiguous recovery are terminal for that owner. Shutdown requests cooperative stop and
joins only for the configured bound. Ownership events use the narrow
`sentientos.maintenance_scheduler_daemon_event:v1` schema and do not duplicate cycle
evidence. The existing `scheduler.lock` remains authoritative and POSIX-only because it
uses `fcntl`; adoption makes no Windows-native claim.
