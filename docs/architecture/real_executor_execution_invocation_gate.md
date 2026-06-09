# Real Executor Execution Invocation Gate

The Real Executor Execution Invocation Gate is a deterministic, metadata-only
verification rung after the merged Real Executor Execution Invocation Packet. It
consumes supplied Real Executor Execution Invocation Packet evidence,
carried-through upstream evidence, and explicit
`real_executor_execution_invocation_gate_candidates` to decide whether a later
Real Executor Execution Preflight Packet may be considered in a separate future
task.

This gate is not executor invocation. It does not invoke an executor, does not
activate an executor, does not release execution, does not issue a permit, does
not authorize execution, does not enable runtime flags, does not acquire locks,
does not create lockfiles, does not perform live memory writes, and does not
grant authority, policy, truth, consent, or permission to execute. Passing this
gate is metadata only and is not permission to execute.

## Inputs

The evaluator requires:

- `real_executor_execution_invocation_packet`: an invocation-packet evidence
  packet with a digest, records, and an invocation-packet decision that is ready,
  warning-ready, or noop for later invocation-gate review.
- `real_executor_execution_invocation_gate_candidates`: explicit candidate
  records whose claimed invocation-packet digest/decision and carried-through
  upstream digest/decision fields match the supplied invocation-packet record.

The carried-through evidence includes activation gate, activation packet,
release gate, release packet, permit gate, permit packet, authorization gate,
authorization packet, execution gate, execution plan, run gate, run packet,
invocation gate, guarded invocation packet, guarded path packet, runtime gate,
runtime enablement packet, live commit execution packet, future execution gate,
constrained enablement path, executor enablement gate, executor skeleton,
invocation harness, activation record, preflight packet, lock lease gate,
executor plan packet, runtime authorization packet, readiness envelope, final
review, real-root admission, and sandbox commit metadata.

## Candidate and decision names

Supported candidate types are the `*_real_executor_execution_invocation_gate_candidate`
forms for AI capsule, human summary, dual capsule, protect receipt, merge
receipt, tomb archive, tomb deferred, operator review, noop, and mixed
diagnostics.

The ready decision is
`real_executor_execution_invocation_gate_ready_for_later_real_executor_execution_preflight_packet`.
Other deterministic decisions are warning-ready, deferred for operator review,
rejected, blocked, and noop. Blocked/invalid/failed outcomes are nonzero CLI
outcomes.

## Produced metadata records

For non-noop candidates the gate emits metadata-only records for:

- invocation-gate readiness;
- invocation-packet confirmation;
- execution-invocation denial;
- final invocation hold points;
- emergency-stop confirmation;
- rollback readiness;
- verification readiness;
- audit readiness.

Every record remains default-deny. Safe next actions are review-only and point to
a separate future Real Executor Execution Preflight Packet request.

## CLI

Use `scripts/build_real_executor_execution_invocation_gate.py`:

```bash
python scripts/build_real_executor_execution_invocation_gate.py build-default
python scripts/build_real_executor_execution_invocation_gate.py validate tests/fixtures/real_executor_execution_invocation_gate/ready_real_executor_execution_invocation_gate_candidate.json
python scripts/build_real_executor_execution_invocation_gate.py evaluate tests/fixtures/real_executor_execution_invocation_gate/ready_real_executor_execution_invocation_gate_candidate.json
python scripts/build_real_executor_execution_invocation_gate.py summarize tests/fixtures/real_executor_execution_invocation_gate/ready_real_executor_execution_invocation_gate_candidate.json
python scripts/build_real_executor_execution_invocation_gate.py inspect-fixture ready_real_executor_execution_invocation_gate_candidate.json
```

`evaluate` prints deterministic JSON and writes nothing.

## Proof and capability

The capability is registered as `real_executor_execution_invocation_gate`, is
covered by focused module and CLI tests, and is included in the memory-chain
matrix runner. The implementation surfaces are
`sentientos/real_executor_execution_invocation_gate.py`,
`scripts/build_real_executor_execution_invocation_gate.py`, deterministic
fixtures under `tests/fixtures/real_executor_execution_invocation_gate/`, and
this architecture note.
