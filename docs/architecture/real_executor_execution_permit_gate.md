# Real Executor Execution Permit Gate

The real executor execution permit gate is a deterministic, metadata-only review
gate that follows the [Real Executor Execution Permit Packet](real_executor_execution_permit_packet.md).
It consumes supplied real executor execution permit packet evidence,
carried-through real executor execution authorization gate, authorization packet,
execution gate, execution plan, run gate, run packet, invocation gate, guarded
invocation packet, guarded path packet, runtime, enablement, live commit, lock,
activation, preflight, final review, real-memory-root, and sandbox evidence plus
explicit real executor execution permit gate candidates to decide whether a
separate, future Real Executor Execution Release Packet may be considered.

This gate is not an execution permit. It does not issue a permit. It is not
execution authorization, permission to execute, a real executor run, executor
execution, executor invocation, real live-memory commit execution, runtime
enablement, runtime flag flipping, an enabled executor, executor enablement,
executor activation, lock acquisition, lockfile creation, memory-root access,
live writes, deletes, purges, index mutation, capsule persistence, tomb
completion, prompt assembly, live context retrieval, action execution, external
disclosure, truth, policy, authority, or consent.

## Evidence relationships

The primary upstream dependency is the real executor execution permit packet. A
real executor execution permit gate candidate must match the permit packet digest
and decision exactly. The gate also requires matching digest and decision
evidence for carried-through records, including the real executor execution
authorization gate, real executor execution authorization packet, real executor
execution gate, real executor execution plan, real executor run gate, real
executor run packet, real executor invocation gate, guarded executor invocation
packet, guarded executor path packet, real executor runtime gate, real executor
runtime enablement packet, live commit execution packet, future live memory
commit execution gate, constrained executor enablement path packet, real
live-memory commit executor enablement gate, executor implementation skeleton,
live executor invocation harness, activation record, preflight packet, lock lease
gate, executor plan packet, explicit runtime execution gate, readiness envelope,
final review gate, real memory-root admission gate, and sandboxed commit adapter.

Scope alignment is required across the real executor execution permit packet
record and the permit gate candidate. Mixed diagnostic candidates may produce
warnings, but warnings do not grant permission, issue a permit, authorize an
executor, activate an executor, enable runtime state, execute an executor, or run
live memory execution.

## Metadata-only records

For non-noop candidates, the evaluator requires and emits deterministic metadata
records for:

- permit-gate readiness;
- permit-packet confirmation;
- execution-permit denial;
- final-permit hold points;
- emergency-stop confirmation;
- rollback readiness;
- verification readiness; and
- audit readiness.

These records are review evidence only. They do not issue an execution permit,
enable an executor, flip a runtime flag, invoke or activate an executor, acquire
or create locks, touch real memory roots, write memory, disclose externally, call
external services, or grant operator consent.

## Candidate types and decisions

Supported candidate types are:

- `ai_capsule_real_executor_execution_permit_gate_candidate`
- `human_summary_real_executor_execution_permit_gate_candidate`
- `dual_capsule_real_executor_execution_permit_gate_candidate`
- `protect_receipt_real_executor_execution_permit_gate_candidate`
- `merge_receipt_real_executor_execution_permit_gate_candidate`
- `tomb_archive_real_executor_execution_permit_gate_candidate`
- `tomb_deferred_real_executor_execution_permit_gate_candidate`
- `operator_review_real_executor_execution_permit_gate_candidate`
- `noop_real_executor_execution_permit_gate_candidate`
- `mixed_real_executor_execution_permit_gate_candidate`

Supported decisions are:

- `real_executor_execution_permit_gate_ready_for_later_real_executor_execution_release_packet`
- `real_executor_execution_permit_gate_ready_with_warnings`
- `real_executor_execution_permit_gate_deferred_for_operator_review`
- `real_executor_execution_permit_gate_rejected`
- `real_executor_execution_permit_gate_blocked`
- `real_executor_execution_permit_gate_noop`

Ready means only that a later Real Executor Execution Release Packet may be
considered in a separate task. It is not safe or authorized to proceed to live
executor execution from this gate alone.

## CLI

`scripts/build_real_executor_execution_permit_gate.py` provides:

- `build-default`
- `evaluate <packet.json>`
- `validate [packet.json]`
- `summarize <packet.json>`
- `inspect-fixture <fixture-name>`

`evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or
failed outcomes exit nonzero. The CLI and library are metadata-only and do not
write memory, delete files, mutate indexes, launch external services, acquire
real locks, create lockfiles, enable executors, flip runtime flags, activate or
invoke executors, execute live commits, issue execution permits, or touch real
memory roots.

## Capability and proof

The capability is registered as `real_executor_execution_permit_gate`, is covered
by `scripts/build_real_executor_execution_permit_gate.py`, and is validated by
`tests/test_real_executor_execution_permit_gate.py` and
`tests/test_build_real_executor_execution_permit_gate_script.py`. Fixture coverage
lives under `tests/fixtures/real_executor_execution_permit_gate/`.
