# Host Embodiment Execution Proof Wing

The Host Embodiment Execution Proof Wing follows Host Embodiment Substrate Phase
5. Phase 5 rehearses fulfillment; this wing defines what any future real host
execution would have to prove before SentientOS could ever perform an effect.

This wing is proof/readiness/supervision scaffolding only. It is not real
actuation, not execution, not host mutation, not direct fan/PWM control, not
thermal actuation, not power profile mutation, not process killing, not service
restart, not package or driver installation, not file cleanup or deletion, not
network egress, not provider invocation, not prompt assembly/export, not
federation transport/sync/adoption, and not remote execution.

## Authority ladder

The authority ladder remains:

`observe → model → propose → broker eligibility → rehearse → readiness → authorization review → authorize → fulfill → effect receipt → postcondition check → audit → rollback`

This wing covers `readiness` and proof scaffolding only; the next wing is `docs/architecture/host_embodiment_authorization_review_wing.md`. It does not authorize,
fulfill, create a real effect receipt, perform postcondition checks against real
effects, audit a real effect, or execute rollback.

## New proof contracts

`sentientos/effect_proof.py` defines metadata-only records:

1. `EffectReceiptContract` — a proof contract for what a future effect receipt
   must bind: source rehearsal receipt, digest, fulfillment domain, backend
   class, effect domain, proof gates, blocked actions, authority references,
   preconditions, postconditions, rollback labels, audit labels, and supervisor
   labels. The Effect Receipt contract is not an effect receipt from a real
   action.
2. `FutureEffectReceipt` — a schema/placeholder for a future receipt. The future
   effect receipt schema is not proof that an effect occurred.
3. `PostconditionCheckPlan` and `PostconditionCheckReceipt` — schema/rehearsal
   records for future postcondition checks. They are schema/rehearsal-only until
   real effects exist.
4. `RollbackPlan` and `RollbackReceipt` — schema/rehearsal records for future
   rollback proof. They are schema/rehearsal-only until real rollback exists.
5. `ExecutionReadinessManifest` — a readiness manifest linking the contract,
   future receipt schema, postcondition plan, rollback plan, optional runtime
   supervisor report, required proof gates, satisfied gates, missing gates, and
   blocked actions. The Execution Readiness Manifest is not authorization.

The future effect receipt schema is not proof that an effect occurred.

## Runtime Supervisor scaffold

`sentientos/runtime_supervisor.py` defines a Runtime Supervisor scaffold for
supplied service/runtime observations. It can record `RuntimeServiceRecord`
metadata, `RuntimeSupervisorSnapshot` telemetry, and
`RuntimeSupervisorReadinessReport` readiness evidence.

The Runtime Supervisor is observation/readiness-only. It does not inspect
privileged live services unless data is supplied, does not restart services,
does not stop services, does not kill processes, does not mutate service
managers, does not install packages, does not mutate host state, and does not
perform network calls. Degraded service records become readiness warnings or
blocked/contradicted reports; they do not become restart authority.

## Proof gates before future effects

Future cooling effects require hardware allowlist, OS backend declaration,
bounds policy, cooldown policy, panic stop, postcondition checks, rollback plan
and rollback receipt, audit receipt, runtime supervisor observation, and
immutable trace. Fan/PWM writes and thermal actuation remain blocked/deferred.

Future power effects require OS backend declaration, bounds/policy gates,
postcondition checks, rollback plan/receipt, audit receipt, runtime supervisor
observation, and immutable trace. Power profile mutation remains
blocked/deferred.

Future cleanup effects require path/file scope, dry-run evidence,
postcondition checks, rollback plan/receipt, audit receipt, runtime supervisor
observation, and immutable trace. File cleanup and file deletion remain
blocked/deferred.

Future service effects require service scope, runtime supervisor observation,
postcondition checks, rollback plan/receipt, audit receipt, and immutable trace.
Service restart and process killing remain blocked/deferred.

Diagnostics and operator-review effects remain readiness-for-authorization-review
only. No effect is performed.

## Pipeline position

The non-mutating pipeline is now:

`collector results → telemetry snapshot → pressure report → policy decision → proposal receipt → broker eligibility decision → broker review receipt → fulfillment rehearsal plan → fulfillment rehearsal receipt → effect receipt contract → future effect receipt schema → postcondition plan → rollback plan → execution readiness manifest → optional runtime supervisor readiness report → authorization review packet → authorization review decision → authorization review receipt → future authorization grant schema`

All stages remain metadata-only and non-mutating. Real fulfillment remains
deferred. Real actuation remains deferred.

## Reviewer proof links

- Module: `sentientos/effect_proof.py`
- Module: `sentientos/runtime_supervisor.py`
- Authorization Review Wing: `docs/architecture/host_embodiment_authorization_review_wing.md`
- Capability registry: `sentientos/capability_registry.py`
- Tests: `tests/test_effect_proof.py`
- Tests: `tests/test_runtime_supervisor.py`
- Registry tests: `tests/test_capability_registry.py`
- Docs regression: `tests/test_reviewer_release_readiness_index.py`

## Named review checklist

Reviewers should explicitly see these proof organs before any future effect:
Effect Receipt contract, Postcondition Check plan/receipt, Rollback Plan/Receipt,
Runtime Supervisor, and Execution Readiness Manifest.
