# Host Embodiment Substrate Phase 1

## Why this exists

Host Embodiment Substrate Phase 1 creates the first concrete organ for the long
trajectory where SentientOS can eventually understand and govern the local
computer from stem to stern. The phase is intentionally limited to
observe/model/propose posture. It adds metadata surfaces that make capability,
hardware/sensor inventory, and resource pressure visible without granting unsafe
host authority.

This phase follows the build order named in
`docs/architecture/sentientos_trajectory_and_missing_organs.md`: Capability
Registry, Hardware/Sensor Inventory Manifest, Host Resource Governor read-only
telemetry, then later Privilege Broker, Actuation Fulfillment Layer, Runtime
Supervisor, and Federation Transport Envelope. It does not skip ahead to host
mutation.

## Implemented now

### Capability Registry

`sentientos/capability_registry.py` defines a machine-readable registry of what
the current node says it can sense, remember, decide, propose, act on, and
federate. The registry is metadata-only. It records implemented, partial,
scaffolded, deferred, blocked, and unknown surfaces with authority levels,
source paths, proof tests, proof commands, deferred surfaces, and forbidden
implications.

The default registry honestly marks GUI/browser host interaction as implemented
but gated, hardware driver awareness as partial, host resource telemetry as
scaffolded, federation evidence custody as implemented, provider invocation as
blocked, and federation transport/sync/adoption as blocked or deferred. Direct
fan/PWM/thermal control and blanket hardware control are blocked/deferred, not
implemented.

### Hardware/Sensor Inventory Manifest

`sentientos/host_inventory.py` represents the local machine body as supplied
metadata: node/host labels, OS family/release/architecture, CPU/GPU/RAM/disk,
network, battery/power, thermal zones, fan/PWM controllers, audio, camera,
display, input, service manager, privilege model, devices, sensors, source
labels, unsupported/deferred labels, and warning/risk codes.

Fan/PWM appears only as inventory and telemetry posture. If no fan/PWM sensors
are supplied, the manifest records `unknown_unavailable_deferred` and
`fan_pwm_control_deferred`; that is not a validation failure and never grants
control.

### Host Resource Governor

`sentientos/host_resource_governor.py` classifies supplied telemetry into labels
such as nominal, CPU pressure, memory pressure, GPU pressure, disk pressure,
thermal pressure, fan signal present, battery pressure, service degraded,
telemetry incomplete, and sensor unavailable. It can emit proposal-only
candidate summaries for future governance, such as reducing model load,
deferring heavy work, requesting operator review, inspecting thermal state,
inspecting disk pressure, inspecting service health, or drafting a future cooling
policy.

Every proposal candidate explicitly states that it is proposal-only, does not
execute, does not mutate the host, and would require a future Privilege Broker,
control-plane admission, operator or policy approval, audit receipt, and rollback
receipt before any future action.

## Deferred and forbidden in Phase 1

Phase 1 does not implement:

- direct fan/PWM writes;
- direct thermal actuation or cooling action;
- power profile changes;
- process killing;
- service restart;
- package installation;
- driver installation or modification;
- host configuration writes;
- provider invocation, prompt export, provider SDK authority, or network egress;
- federation transport, sync, adoption, merge, apply, install, execution, or
  remote execution;
- production execution from readiness/proposal artifacts;
- unapproved self-modification.

direct fan/PWM control remains deferred because safe host-resource action needs
more than telemetry. It requires policy, hardware allowlists, a Privilege Broker,
operator override, panic handling, control-plane admission, fulfillment receipts,
audit receipts, and rollback receipts. Thermal control is likewise deferred
until a later phase proves the complete authority and recovery chain.

## Future ladder

Every new class of host control must pass through this ladder:

`telemetry → proposal → privilege broker → fulfillment → audit → rollback`

The longer doctrine remains:

`observe → model → propose → rehearse → authorize → fulfill → audit → rollback`

Phase 1 covers observe/model and proposal candidate summaries only. It never
fulfills an action.

## Relationship to existing organs

- GUI/browser control remains bounded and gated through existing shims and audit
  posture; registry entries do not convert it into blanket host control.
- `sentientos/daemons/driver_manager.py` remains hardware/driver awareness and
  recommendation posture; Phase 1 does not install drivers.
- The embodiment pipeline (`embodiment_fusion`, `embodiment_ingress`,
  `embodiment_proposals`, `embodiment_governance_bridge`, and
  `embodiment_fulfillment`) remains evidence, proposal, review, bridge, and
  non-authoritative fulfillment-candidate posture; receipts are not effects.
- `sentientos/control_plane_kernel.py` remains the admission surface for governed
  work; Phase 1 does not add a bypass around it.
- The autonomy runtime and future Runtime Supervisor remain composition and
  health/safe-shutdown concerns, not uncontrolled authority expansion.

## Proof commands

```bash
python -m scripts.run_tests -q tests/test_capability_registry.py tests/test_host_inventory.py tests/test_host_resource_governor.py
python -m scripts.run_tests -q tests/test_reviewer_release_readiness_index.py
python scripts/verify_context_hygiene_prompt_boundaries.py
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
```
