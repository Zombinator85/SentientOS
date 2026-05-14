# Host Actuation Safety Gate Wing

This wing follows the [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md) and the [Reviewer First-Run Proof Bundle](reviewer_first_run_proof_bundle.md). It adds metadata-only safety gates that define what future host actuation must declare and satisfy before live authorization could even be reviewed.

## Boundary

This is a safety-gate/proof wing only. Controlled authorization contract is not a live grant. Safety gates are not authorization. SafetyGateSatisfactionManifest is not authorization or fulfillment. Real fulfillment remains deferred. Real actuation remains deferred.

The wing does not execute, fulfill, mutate host state, write fan/PWM controls, change thermal settings, mutate power profiles, kill processes, restart services, clean up or delete files, install packages or drivers, perform network egress, invoke providers, assemble or export prompts, transport federation state, or perform remote execution.

## Safety records

- **Hardware Allowlist Manifest:** declares hardware metadata and domain eligibility. Hardware allowlist does not grant control.
- **OS Backend Declaration:** declares the future backend class and OS family. OS backend declaration does not load/invoke backend.
- **Bounds Policy:** declares future bounds/rates/forbidden values. Bounds policy does not enforce live bounds.
- **Cooldown Policy:** declares future intervals/attempt limits. Cooldown policy does not sleep, wait, or enforce live cooldown.
- **Panic Stop Contract:** declares future triggers, stops, operator overrides, and recovery labels. Panic stop contract does not execute panic stop.
- **Host Action Scope Manifest:** declares target/path/service/hardware/time/expiry/revocation scope. Scope manifest does not authorize action.
- **Host Actuation Gate Assessment:** evaluates whether a gate has metadata evidence or is missing.
- **SafetyGateSatisfactionManifest:** summarizes satisfied and missing gates plus blocked actions; it is not authorization or fulfillment.

## Future gate requirements

Future cooling/power/service/cleanup actions remain behind explicit future live authorization, control-plane admission, audit, rollback, effect receipt, postcondition checks, supervisor observation, immutable trace, and these safety gates. Future fan/PWM writes, thermal actuation, power profile mutation, service restart, process kill, cleanup/delete, package install, driver install, network egress, provider invocation, prompt assembly, federation transport, and remote execution remain blocked/deferred by this wing.

## Authority ladder

The authority ladder remains:

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → authorize → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers **safety gates** only. It answers: “What gates must be declared, checked, and satisfied before future live authorization could even be reviewed?” It does not answer: “Perform the action.”

## Implementation links

- Module: `sentientos/host_actuation_safety.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_host_actuation_safety.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_capability_registry.py`
