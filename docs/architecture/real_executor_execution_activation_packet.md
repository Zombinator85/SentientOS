# Real Executor Execution Activation Packet

The Real Executor Execution Activation Packet is a deterministic, metadata-only
review bundle for the next separate memory-chain rung after the merged Real
Executor Execution Release Gate. It consumes supplied Real Executor Execution
Release Gate evidence, carried-through upstream evidence, and explicit
`real_executor_execution_activation_packet_candidates` to produce reviewable
activation-packet metadata for a later Real Executor Execution Activation Gate.

This packet is not executor activation. It does not activate an executor, does
not release execution, does not issue a permit, does not authorize execution,
does not invoke an executor, does not enable runtime flags, does not acquire
locks, does not create lockfiles, does not perform live memory writes, and does
not grant authority, policy, truth, consent, or permission to execute.

## Inputs

The evaluator requires:

- `real_executor_execution_release_gate`: a release-gate packet with a digest,
  records, and a release-gate decision that is ready, warning-ready, or noop for
  later activation-packet review.
- `real_executor_execution_activation_packet_candidates`: explicit candidate
  records whose claimed release-gate digest/decision and carried-through
  upstream digest/decision fields match the supplied release-gate record.

The carried-through evidence includes release packet, permit gate, permit
packet, authorization gate, authorization packet, execution gate, execution
plan, run gate, run packet, invocation gate, guarded invocation packet, guarded
path packet, runtime gate, runtime enablement packet, live commit execution
packet, future execution gate, constrained enablement path, executor enablement
gate, executor skeleton, invocation harness, activation record, preflight
packet, lock lease gate, executor plan packet, runtime authorization packet,
readiness envelope, final review, real-root admission, and sandbox commit
metadata.

## Candidate and decision names

Supported candidate types are the `*_real_executor_execution_activation_packet_candidate`
forms for AI capsule, human summary, dual capsule, protect receipt, merge
receipt, tomb archive, tomb deferred, operator review, noop, and mixed
diagnostics.

The ready decision is
`real_executor_execution_activation_packet_ready_for_later_real_executor_execution_activation_gate`.
Other deterministic decisions are warning-ready, deferred for operator review,
rejected, blocked, and noop. Blocked/invalid/failed outcomes are nonzero CLI
outcomes.

## Produced metadata records

For non-noop candidates the packet emits metadata-only records for:

- activation-packet readiness;
- release-gate confirmation;
- execution-activation denial;
- final activation hold points;
- emergency-stop confirmation;
- rollback readiness;
- verification readiness;
- audit readiness.

Every record remains default-deny. Safe next actions are review-only and point to
a separate future Real Executor Execution Activation Gate request.

## CLI

Use `scripts/build_real_executor_execution_activation_packet.py`:

```bash
python scripts/build_real_executor_execution_activation_packet.py build-default
python scripts/build_real_executor_execution_activation_packet.py validate tests/fixtures/real_executor_execution_activation_packet/ready_real_executor_execution_activation_packet_candidate.json
python scripts/build_real_executor_execution_activation_packet.py evaluate tests/fixtures/real_executor_execution_activation_packet/ready_real_executor_execution_activation_packet_candidate.json
python scripts/build_real_executor_execution_activation_packet.py summarize tests/fixtures/real_executor_execution_activation_packet/ready_real_executor_execution_activation_packet_candidate.json
python scripts/build_real_executor_execution_activation_packet.py inspect-fixture ready_real_executor_execution_activation_packet_candidate.json
```

`evaluate` prints deterministic JSON and writes nothing.

## Proof and capability

The capability is registered as `real_executor_execution_activation_packet`, is
covered by focused module and CLI tests, and is included in the memory-chain
matrix runner. The implementation surfaces are
`sentientos/real_executor_execution_activation_packet.py`,
`scripts/build_real_executor_execution_activation_packet.py`, deterministic
fixtures under `tests/fixtures/real_executor_execution_activation_packet/`, and
this architecture note.
