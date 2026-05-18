# Host Embodiment Substrate Phase 3: Policy Receipts

Phase 3 converts read-only host resource pressure reports into deterministic,
auditable, proposal-only policy decisions and proposal receipts. It is the
`propose` rung of the authority ladder and nothing more.

`observe → model → propose → rehearse → authorize → fulfill → audit → rollback`

Phase 3 consumes the Phase 1/2 pipeline:

`collector results → HostResourceTelemetrySnapshot → HostResourcePressureReport → HostResourcePolicyDecision → HostResourceProposalReceipt(s)`

## Core boundary

Pressure is not action. A CPU, memory, GPU, disk, thermal, fan, service, or
incomplete telemetry label may justify a policy proposal receipt, but the receipt
is not an effect. Proposal receipts are not effects. They do not execute, do not
mutate the host, do not authorize fulfillment, and do not bypass the control
plane.

A policy decision is not authorization. It records that a deterministic policy
rule classified a pressure report and selected proposal kinds for review,
diagnostics, rehearsal, or a future broker queue. It does not grant privilege,
control devices, alter power profiles, restart services, clean disks, kill
processes, install packages, install drivers, call providers, assemble prompts,
perform network egress, sync federation state, or execute remotely.

## Implemented surfaces

`sentientos/host_resource_policy.py` defines immutable metadata records for:

- `HostResourcePolicyRule`
- `HostResourcePolicyDecision`
- `HostResourceProposalReceipt`
- `HostResourcePolicyValidationResult`

The module also exposes deterministic helpers for default rules, policy
evaluation, proposal receipt construction, validation, summaries, and digests.
The summaries intentionally expose ids, statuses, counts, labels, booleans, and
digests rather than raw host-sensitive telemetry.

## Proposal mapping

- CPU pressure can record `inspect_cpu_pressure_candidate`,
  `reduce_model_load_candidate`, and `defer_heavy_task_candidate`.
- Memory pressure can record `inspect_memory_pressure_candidate` and
  `defer_heavy_task_candidate`.
- GPU pressure can record `inspect_gpu_pressure_candidate`,
  `reduce_model_load_candidate`, and `defer_heavy_task_candidate`.
- Disk pressure can record `inspect_disk_pressure_candidate` and a blocked
  `future_cleanup_policy_candidate`.
- Thermal pressure can record `inspect_thermal_state_candidate` and a blocked
  `future_cooling_policy_candidate`.
- Fan RPM/PWM observations are diagnostics/monitoring only unless paired with
  thermal pressure. PWM presence is not control authority.
- Service degradation can record `inspect_service_health_candidate`, not a
  restart.
- Incomplete telemetry can record diagnostics/operator-review proposals only.
- Unknown or contradictory reports block proposal readiness.

## Future-only candidates

Future cooling, power, service, and cleanup candidates remain future-only. Phase 3 names the future Privilege Broker and Actuation Fulfillment Layer without implementing either organ. They
are explicit handoff material for a later Privilege Broker and Actuation
Fulfillment Layer after separate authorization exists. A future fulfillment path
must still provide control-plane admission, operator or policy approval, audit
receipt, rollback receipt, panic handling, and hardware/policy allowlists as
appropriate.

Thermal pressure can justify inspection/proposal, not fan control. PWM presence
is not control authority. Service degradation can justify review/proposal, not
restart. Disk pressure can justify inspection/proposal, not cleanup.

## Explicit non-effects

Every Phase 3 proposal receipt records that it is proposal-only, does not
execute, does not mutate host state, is not authorized for fulfillment, requires
a future Privilege Broker, requires control-plane admission, requires operator or
policy approval, requires an audit receipt, and requires a rollback receipt.

Blocked action labels include host mutation, fan/PWM writes, thermal actuation,
process kill, service restart, package install, driver install, provider
invocation, network egress, prompt assembly, federation transport/sync/adoption,
and remote execution.

## Proof commands

```bash
python -m scripts.run_tests -q tests/test_host_resource_policy.py tests/test_host_resource_governor.py tests/test_capability_registry.py
python -m scripts.run_tests -q tests/test_reviewer_release_readiness_index.py
python scripts/verify_context_hygiene_prompt_boundaries.py
python scripts/build_docs.py --check-deps
python scripts/build_docs.py --bootstrap-docs
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
```

Phase 4 privilege broker eligibility is documented in `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`. Phase 5 actuation fulfillment rehearsal is documented in `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md`. Eligibility is not authorization, broker receipts are not fulfillment, and fulfillment rehearsal is not real fulfillment.


## Host Embodiment Execution Proof Wing

Next proof/readiness wing: `docs/architecture/host_embodiment_execution_proof_wing.md`. Execution readiness is not authorization; the future effect receipt schema is not proof of effect; the Runtime Supervisor does not restart/kill services; real actuation remains deferred.
