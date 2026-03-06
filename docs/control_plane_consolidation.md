# Control-Plane Consolidation Pass

## Runtime Actuation Path Discovery (verified before refactor)

Execution-capable runtime mutation paths identified:

1. **Daemon restart actuation**
   - Entry: `daemon_manager._DaemonManager.restart`
   - Triggered by local calls and federated pulse `restart_daemon` payloads.
2. **Repair action execution**
   - Entry: `sentientos.codex_healer.CodexHealer._handle_anomaly`
   - Applies synthesized repair actions and regenesis fallback.
3. **Federated control ingestion**
   - Entry: `sentientos.daemons.pulse_federation.ingest_remote_event`
   - Admits/rejects signed remote control events.
4. **Control-plane task admission and execution**
   - Entry: `control_plane.task_admission.admit_request`
   - Generates execution authorization consumed by task/speech/self-patching paths.
5. **Governance amendment apply class (admission surface)**
   - Consolidated in `RuntimeGovernor.admit_action("amendment_apply", ...)` for deterministic routing.

## Previous Admission Layering (before consolidation)

- `RuntimeGovernor.admit_restart`, `admit_repair`, `admit_federated_control` (partial).
- `control_plane/task_admission.py` static policy/rate/human checks without governor authority.
- `control_plane/policy.py` request rules and rate constraints.
- `daemon_manager` restart path checked governor directly via restart-specific method.
- `CodexHealer` checked governor via repair-specific method.
- `pulse_federation` checked governor via federated-specific method.

Redundancy/bypass concern: control-plane authorization (TASK_EXECUTION and related execution grants) could be admitted without governor-based pressure/storm gate.

## Unified Interface

`RuntimeGovernor` now exposes:

```python
governor.admit_action(action_type, actor, correlation_id, metadata)
```

Supported `action_type` values:
- `restart_daemon`
- `repair_action`
- `federated_control`
- `control_plane_task`
- `amendment_apply`

## Consolidated Routing

- `control_plane/task_admission.admit_request` now delegates to `admit_action("control_plane_task", ...)`.
- `daemon_manager` restart path now uses `admit_action("restart_daemon", ...)` once.
- `CodexHealer` repair path now uses `admit_action("repair_action", ...)`.
- `pulse_federation` ingress now uses `admit_action("federated_control", ...)`.
- Legacy policy modules remain, but task admission now composes static policy checks with governor decision.

## Audit Artifacts

All governor decisions written under `/glow/governor/` include:
- `correlation_id`
- `decision`
- `reason`
- `governor_mode`
- `pressure_snapshot`

And are emitted as pulse events via governor decision publishing.

## Control-Plane Architecture Diagram

```mermaid
flowchart TD
    A[Actors: operator/codex/peer] --> B[Action Request]
    B --> C{RuntimeGovernor.admit_action}

    C -->|allow| D[Actuation Path]
    C -->|deny| E[Deterministic Deny]

    D --> D1[daemon_manager.restart]
    D --> D2[CodexHealer.apply]
    D --> D3[pulse_federation.ingest]
    D --> D4[control_plane.task_admission token]

    C --> F[/glow/governor/decisions.jsonl]
    C --> G[pulse_bus governor_decision event]

    H[control_plane.policy static rules] --> D4
    I[federation trust/signature checks] --> D3
```

## Minimal Refactor Plan Applied

1. Add generic `admit_action` router in RuntimeGovernor.
2. Add governor-native handlers for control-plane tasks and amendment apply.
3. Extend decision payload with canonical audit fields (`decision`, `governor_mode`, `pressure_snapshot`).
4. Repoint restart/repair/federated callsites to unified governor entrypoint.
5. Repoint control-plane task admission to governor while preserving deterministic static policy invariants.
6. Add focused tests for router behavior and admission artifact propagation.

