# Host Dry-Run Execution Runtime

The host dry-run execution runtime closes the simulation-only loop between the exact host fulfillment executor-contract readiness runtime package and the existing deterministic dry-run execution harness.

It accepts only a complete `HostFulfillmentExecutorReadinessEvaluation` (or strict CLI JSON for that full graph), not a standalone readiness receipt. The source chain binds the readiness request, runtime plan, historical/current authority evidence, current snapshot reference, metadata admission, prerequisite records, executor contract, backend declaration, precondition manifest, declarative dry-run plan, future-execution admission packet, executor-contract readiness receipt, readiness runtime receipt, and a deterministic source bundle digest.

The runtime may truthfully report that an in-process deterministic simulation ran. It never reports or implies that a real executor ran. It does not load or invoke real backends, request future-execution admission, request privileged-effect admission, grant fulfillment, mutate host state, perform real postconditions, perform real rollback, or produce a real effect receipt.

## Current-authority boundary

The executor-readiness source must already contain current authority evidence from the exact current-authority snapshot flow. If the readiness package is stale, contradicted, blocked, unavailable, missing the runtime receipt, missing current-authority evidence, or has any authority/effect flag set true, the dry-run runtime blocks before simulation admission. In those blocked postures, simulation admission call count, harness-builder call count, and simulation call count remain zero.

## Simulation admission

The runtime requests only `PROPOSAL_EVALUATION` metadata admission for simulation review. That admission binds the runtime request digest, source readiness evaluation digest, source readiness bundle digest, current snapshot/evidence digest, executor contract digest, declarative dry-run plan digest, simulated backend registry digest, correlation ID, and all no-real-execution assertions. Deny, defer, quarantine, malformed, stale, missing, or contradictory admission blocks before the dry-run harness is called.

## Harness composition and lineage

The runtime reuses `sentientos/dry_run_execution_harness.py` for policy, simulated backend registry, dry-run request, simulation result/block receipt, and dry-run receipt construction. The harness records now include parent lineage fields for readiness runtime receipt, executor contract, declarative dry-run plan, current snapshot, simulated registry, request digest, result digest, and finding digests. Changing a semantic parent changes dependent identities.

Executor domains map deterministically to simulated dry-run domains. Cooling, power, cleanup, service, diagnostics, thermal-safety, resource-pressure, and operator-review executors map only to their corresponding inert simulated dry-run domains and backend classes. Arbitrary backend labels, module paths, filesystem paths, URLs, import labels, callable names, command fragments, environment interpolation, and serialized executable content are not runtime backend targets.

## Persistence and replay

When successful, the runtime writes an atomic external bundle under the caller-supplied output root. The bundle includes runtime request, source manifest, runtime plan, simulation admission, harness policy, simulated backend registry, dry-run request, result or block receipt, dry-run receipt, validation findings, runtime receipt, summary, Markdown, and deterministic bundle manifest. `latest.json` and `replay_index.json` are updated atomically. Replay validates every manifest entry by digest and byte size and performs zero new admission, builder, or simulation calls.

Repository-local output roots and symlink escapes are rejected. Corrupt prior bundles fail closed. A same-correlation semantic conflict is contradicted rather than re-run.

## Daemon, World-State, and dashboard

`sentientosd` remains non-requesting, non-admitting, non-simulating, non-executing, and non-fulfilling. The runtime exposes World-State facts only as proposal/review/rehearsal evidence. The authenticated dashboard route `/api/world-state/host-dry-run-execution` reads the terminal World-State snapshot and is read-only; dashboard reads do not call the runtime, control-plane admission, harness builders, or simulation.

## Capability posture

The capability registry entry `host_dry_run_execution_runtime` marks the chain implemented as simulation-only. Real executor implementation, real backend loading, real backend invocation, future-execution admission, fulfillment, privileged-effect admission, host mutation, and effect proof remain deferred or absent.
