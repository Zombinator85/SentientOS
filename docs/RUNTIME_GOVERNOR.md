# Runtime Governor

SentientOS includes a deterministic Runtime Governor admissibility layer for
control-plane pacing and storm control. The governor does not replace authority
validation; it decides whether valid actions may execute right now.

## Scope

The governor evaluates:

- daemon restart actions
- CodexHealer repair actions
- federated control actions
- high-frequency pulse critical events

The governor persists append-only decision telemetry and pressure snapshots at:

- `/glow/governor/decisions.jsonl`
- `/glow/governor/pressure.jsonl`
- `/glow/governor/storm_budget.json`

## Modes

Set `SENTIENTOS_GOVERNOR_MODE` to one of:

- `shadow` (default): log decisions; do not block execution
- `advisory`: log warning decisions; do not block execution
- `enforce`: deny actions that exceed storm budgets or pressure thresholds

## Deterministic controls

- fixed-window restart limits per daemon
- fixed-window repair limits per anomaly class
- federated control rate limit window
- critical-event storm threshold
- pressure threshold gates

## Deterministic arbitration model

RuntimeGovernor applies fixed class semantics before final allow/deny:

- `restart_daemon`: priority `0`, family `recovery` (non-deferrable)
- `repair_action`: priority `1`, family `recovery` (non-deferrable)
- `federated_control`: priority `2`, family `federated` (deferrable)
- `control_plane_task`: priority `3`, family `control_plane` (deferrable)
- `amendment_apply`: priority `4`, family `amendment` (deferrable)

Arbitration uses deterministic fixed windows and caps:

- contention window (`SENTIENTOS_GOVERNOR_CONTENTION_WINDOW_SECONDS`)
- total contention cap (`SENTIENTOS_GOVERNOR_CONTENTION_LIMIT`)
- reserved contention slots for recovery paths (`SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS`)
- warn-pressure low-priority cap (`SENTIENTOS_GOVERNOR_WARN_LOW_PRIORITY_LIMIT`)
- storm-time federated cap (`SENTIENTOS_GOVERNOR_STORM_FEDERATED_LIMIT`)

Under pressure or storm conditions, deferrable classes can be denied with explicit
defer reasons, while local recovery paths keep precedence to avoid starvation.
Every decision records `correlation_id`, `decision`, `reason`, `governor_mode`,
`pressure_snapshot`, `action_priority`, and `action_family`.

All denials emit signed pulse events:

- `governor_state`
- `governor_decision`

These events flow through the standard pulse signing model and remain auditable.

## Rollout guidance

1. Shadow mode in production and CI baseline capture.
2. Advisory mode with alerting and no action blocking.
3. Enforcement mode once thresholds are tuned and replay evidence is stable.

## Rollback switch

Set:

```bash
SENTIENTOS_GOVERNOR_MODE=shadow
```

to disable blocking while retaining observability.
