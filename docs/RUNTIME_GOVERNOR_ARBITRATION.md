# RuntimeGovernor Arbitration Hardening Note

## Goal

Preserve deterministic, auditable admission while resolving contention between valid
runtime action classes without adaptive or reward-driven behavior.

## Action classes and fixed semantics

RuntimeGovernor assigns every admitted action class a static profile:

- `restart_daemon`: priority `0`, family `recovery`, non-deferrable
- `repair_action`: priority `1`, family `recovery`, non-deferrable
- `federated_control`: priority `2`, family `federated`, deferrable
- `control_plane_task`: priority `3`, family `control_plane`, deferrable
- `amendment_apply`: priority `4`, family `amendment`, deferrable

Lower integer priority means higher precedence.

## Deterministic arbitration rules

Arbitration is applied after existing per-class budgets and pressure gates. Rules are
ordered and deterministic:

1. **Local safety precedence under pressure**: deferrable federated actions are denied
   under blocking pressure to reserve capacity for local safety recovery.
2. **Warn-pressure low-priority throttling**: control-plane task and amendment traffic
   can be deferred once a fixed warn-level burst cap is reached.
3. **Storm-time federated throttling**: federated controls are deferred once a fixed
   storm/warn cap is reached.
4. **Recovery reservation**: non-recovery classes are deferred when remaining contention
   slots are at or below a reserved recovery floor.
5. **Recovery anti-starvation override**: recovery actions remain admissible when
   contention limits are saturated.

## Bounded contention accounting

Only allowed actions are counted in a fixed contention window. The governor records
windowed contention counts and exposes limits in `storm_budget.json`.

## Auditability

Every decision (allow, defer, deny) emits immutable telemetry with:

- `correlation_id`
- `decision`
- `reason`
- `governor_mode`
- `pressure_snapshot`
- `action_priority`
- `action_family`

This preserves append-only provenance and deterministic replay expectations.
