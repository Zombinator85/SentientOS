# Initial POSIX resident commissioning authority

`maintenance_initial_posix_resident_commissioning` is a governance-only authority
definition for a future, separately admitted initial commissioning implementation. The
definition is registered; runtime commissioning is not implemented. Registration grants
no capability, performs no runtime effect, creates no external custody or generation-zero
record, and launches no process.

## Why this boundary precedes resident adoption

`maintenance_resident_runtime_adoption` correctly begins only after a verified successor
maintenance generation, pending successor handoff, exact successor repository state, and
predecessor resident launch provenance exist. Initial commissioning necessarily precedes
all of those facts. Reusing or weakening that successor-only contract would fabricate its
preconditions and collapse distinct authority boundaries.

The causal ordering is therefore:

```text
operator-approved initial commissioning
-> generation 0 / initial lineage
-> first canonical resident launch
-----------------------------------------
future boundary
-----------------------------------------
successful maintenance change
-> continuity N+1
-> successor handoff
-> resident self-replacement
```

Initial resident commissioning, successor authority-generation adoption, and resident
runtime successor adoption remain three separate concepts. The first establishes the
initial condition. It cannot select or advance a successor, self-replace resident code,
or authorize recurring adoption.

## Exact future authority definition

The future capability is limited to the `maintenance` subsystem and the principal
`deterministic_maintenance_initial_posix_resident_commissioning_controller`. A later
effectful task must request the complete exact effect set declared by
`MAINTENANCE_INITIAL_POSIX_RESIDENT_COMMISSIONING_DEFINITION`: exact initial repository,
POSIX-host, launch-target, and maintenance-profile inspection; bounded external initial
custody; generation-zero policy and configuration creation; immutable provenance and
receipt custody; one exact initial `sentientosd` launch; and read-only health projection.

Every later task must affirm operator-approved initial POSIX commissioning, exact initial
repository and POSIX-host identity, explicit bounded initial maintenance authority,
external custody, a generation-zero lineage, the exact launch contract, one bounded
initial launch, and separate successor-adoption authority. Explicit operator approval,
exact control-plane admission, and durable audit/receipt evidence remain separate from
definition eligibility and from the runtime effect.

The contract rejects arbitrary process, executable, argv, environment, command, shell,
service, repository, commit, or generation control; authority widening or expiry
extension; automatic or recurring adoption; rollback; Git fetch, pull, push, or
publication; repository mutation; provider, network, or credential authority; OS service
installation; systemd or Windows service/replacement authority; candidate admission;
maintenance implementation or validation; and model- or cognition-derived authorization.

## Registration posture and next task

This registration is structural only. It does not run a host doctor, create a continuity
policy, create generation zero, create adoption configuration, call `os.execve`, launch
`sentientosd`, or emit commissioning/adoption receipts. The capability registry therefore
marks only the contract and admission surfaces as present and lists all runtime work as
deferred.

The immediate next task is: implement and exercise
`maintenance_initial_posix_resident_commissioning` under its newly registered exact
authority definition, creating generation zero and the first canonical POSIX resident if
the host qualifies; then hand all later software succession back to the existing
successor-generation and resident-runtime adoption capabilities.

