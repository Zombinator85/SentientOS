# Real Executor Execution Authorization Packet

The real executor execution authorization packet is a deterministic,
metadata-only review packet that follows the [Real Executor Execution Gate](real_executor_execution_gate.md).
It consumes supplied real executor execution gate evidence plus explicit real
executor execution authorization packet candidates to decide whether a separate,
future Real Executor Execution Authorization Gate may be considered.

This packet is not execution authorization. It is not permission to execute, a
real executor run, executor execution, executor invocation, real live-memory
commit execution, runtime enablement, runtime flag flipping, an enabled executor,
executor enablement, executor activation, lock acquisition, lockfile creation,
memory-root access, live writes, deletes, purges, index mutation, capsule
persistence, tomb completion, prompt assembly, live context retrieval, action
execution, external disclosure, truth, policy, authority, or consent.

## Evidence relationships

The primary upstream dependency is the real executor execution gate. A real
executor execution authorization packet candidate must match the execution gate
digest and decision exactly. The packet also carries forward matching digest and
decision evidence for the real executor run gate, real executor run packet, real
executor invocation gate, guarded executor invocation packet, guarded executor
path packet, real executor runtime gate, real executor runtime enablement packet,
live commit execution packet, future live memory commit execution gate,
constrained executor enablement path packet, real live-memory commit executor
enablement gate, executor implementation skeleton, live executor invocation
harness, activation record, preflight packet, lock lease gate, executor plan
packet, explicit runtime execution gate, readiness envelope, final review gate,
real memory-root admission gate, and sandboxed commit adapter.

Scope alignment is required across the real executor execution gate record and
the authorization packet candidate. Mixed diagnostic candidates may produce
warnings, but warnings do not grant permission, authority, executor activation,
runtime enablement, executor execution, or live execution.

## Metadata-only records

For non-noop candidates, the evaluator requires and emits deterministic metadata
records for:

- authorization-packet readiness;
- execution-gate confirmation;
- execution-authority denial;
- final authorization hold points;
- emergency-stop confirmation;
- rollback readiness;
- verification readiness; and
- audit readiness.

These records are review evidence only. They do not enable an executor, flip a
runtime flag, invoke or activate an executor, acquire or create locks, touch real
memory roots, write memory, disclose externally, call external services, or grant
operator consent.

## Candidate types and decisions

Supported candidate types are:

- `ai_capsule_real_executor_execution_authorization_packet_candidate`
- `human_summary_real_executor_execution_authorization_packet_candidate`
- `dual_capsule_real_executor_execution_authorization_packet_candidate`
- `protect_receipt_real_executor_execution_authorization_packet_candidate`
- `merge_receipt_real_executor_execution_authorization_packet_candidate`
- `tomb_archive_real_executor_execution_authorization_packet_candidate`
- `tomb_deferred_real_executor_execution_authorization_packet_candidate`
- `operator_review_real_executor_execution_authorization_packet_candidate`
- `noop_real_executor_execution_authorization_packet_candidate`
- `mixed_real_executor_execution_authorization_packet_candidate`

Supported decisions are:

- `real_executor_execution_authorization_packet_ready_for_later_real_executor_execution_authorization_gate`
- `real_executor_execution_authorization_packet_ready_with_warnings`
- `real_executor_execution_authorization_packet_deferred_for_operator_review`
- `real_executor_execution_authorization_packet_rejected`
- `real_executor_execution_authorization_packet_blocked`
- `real_executor_execution_authorization_packet_noop`

Ready means only that a later Real Executor Execution Authorization Gate may be
considered in a separate task. It is not safe or authorized to proceed to live
executor execution from this packet alone.

## CLI

`scripts/build_real_executor_execution_authorization_packet.py` provides:

- `build-default`
- `evaluate <packet.json>`
- `validate [packet.json]`
- `summarize <packet.json>`
- `inspect-fixture <fixture-name>`

`evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or
failed outcomes exit nonzero. The CLI and library are metadata-only and do not
write memory, delete files, mutate indexes, launch external services, acquire
real locks, create lockfiles, enable executors, flip runtime flags, activate or
invoke executors, execute live commits, or touch real memory roots.

## Capability and proof

The capability is registered as `real_executor_execution_authorization_packet`,
is covered by `scripts/build_real_executor_execution_authorization_packet.py`,
and is validated by `tests/test_real_executor_execution_authorization_packet.py`
and `tests/test_build_real_executor_execution_authorization_packet_script.py`.
Fixture coverage lives under
`tests/fixtures/real_executor_execution_authorization_packet/`.
