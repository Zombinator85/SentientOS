# Guarded Executor Invocation Packet

The guarded executor invocation packet is a deterministic, metadata-only review
packet after the [Guarded Executor Path Packet](guarded_executor_path_packet.md).
It exists to make a later real executor invocation gate reviewable without
invoking, activating, enabling, or executing any executor now. The packet consumes
supplied guarded executor path packet evidence plus explicit guarded invocation
candidates and verifies that every candidate repeats the exact upstream digest
and decision evidence carried by the guarded executor path packet.

This packet is not real live-memory commit execution. It is not executor
invocation, runtime enablement, runtime flag flipping, executor enablement,
executor activation, lock acquisition, lockfile creation, memory-root access,
live writes, deletes, purges, index mutation, capsule persistence, tomb
completion, prompt assembly, live context retrieval, action execution, external
disclosure, truth, policy, authority, or consent.

## Evidence relationships

The primary upstream dependency is the guarded executor path packet. A guarded
invocation candidate must match the guarded executor path packet digest and the
path decision exactly. Guarded path readiness is not permission to invoke; it is
only evidence that this downstream invocation packet may be drafted for review.

The packet also verifies the digest and decision evidence carried forward from:

- [Real Executor Runtime Gate](real_executor_runtime_gate.md): runtime gate
  readiness is not permission to execute.
- [Real Executor Runtime Enablement Packet](real_executor_runtime_enablement_packet.md):
  runtime enablement packet readiness is not permission to flip flags.
- [Live Commit Execution Packet](live_commit_execution_packet.md): execution
  packet readiness is not permission to execute; operation bundle records remain
  intents only.
- [Future Live Memory Commit Execution Gate](future_live_memory_commit_execution_gate.md):
  future execution gate readiness is not permission to execute.
- [Constrained Executor Enablement Path Packet](constrained_executor_enablement_path_packet.md):
  constrained path readiness is not executor enablement.
- [Real Live Memory Commit Executor Enablement Gate](real_live_memory_commit_executor_enablement_gate.md):
  enablement-gate evidence is not executor enablement.
- [Real Live Memory Commit Executor Implementation Skeleton](real_live_memory_commit_executor_implementation_skeleton.md):
  skeleton records are not executed operations.
- [Live Executor Invocation Harness](live_executor_invocation_harness.md):
  invocation readiness is not live execution.
- [Live Executor Activation Record](live_executor_activation_record.md):
  activation readiness is not live execution.
- [Live Executor Preflight Packet](live_executor_preflight_packet.md): preflight
  readiness is not live execution.
- [Live Executor Lock Lease Gate](live_executor_lock_lease_gate.md): lock lease
  readiness is not real lock acquisition and does not inspect or create real
  lockfiles.
- [Real Live Memory Commit Executor Plan Packet](real_live_memory_commit_executor_plan_packet.md):
  executor plan operation records are intents only.
- [Explicit Live Memory Runtime Execution Gate](explicit_live_memory_runtime_execution_gate.md):
  runtime execution gate readiness is not execution.
- [Real Live Memory Commit Adapter Readiness Envelope](real_live_memory_commit_adapter_readiness_envelope.md):
  readiness envelope evidence is not runtime permission.
- [Final Live Memory Commit Review Gate](final_live_memory_commit_review_gate.md):
  final review is not execution permission.
- [Real Memory Root Admission Gate](real_memory_root_admission_gate.md):
  real-root admission is not memory-root access.
- [Sandboxed Live Memory Commit Adapter](sandboxed_live_memory_commit_adapter.md):
  sandbox commits are not real commits, sandbox receipts are not live receipts,
  and sandbox rollback manifests are not applied rollback.

The packet remains downstream of the live commit safety interlock, live memory
commit dry-run adapter, memory commit execution gate, memory commit operator
approval packet, memory commit plan packet, live memory boundary admission gate,
governed memory writer adapter, selective memory tomb receipt verifier,
selective memory distillation receipt gate, and selective memory distillation
contract. It does not bypass those layers.

## Metadata-only records

For non-noop candidates, the evaluator requires metadata for invocation-packet
readiness, guarded invocation prerequisites, invocation hold points,
runtime-guard confirmations, emergency-stop confirmation, rollback readiness,
verification readiness, audit readiness, guarded invocation operator
acknowledgement, final hold points, receipt expectations, rollback expectations,
verification gates, audit gates, idempotency keys, atomicity boundaries,
execution windows, operator identity and role, clean-tree expectations, and
scope alignment.

These records are deterministic metadata only. Invocation-packet readiness is not
permission to invoke. Guarded invocation prerequisites are not executor
invocation. Invocation hold points and guarded invocation final hold points are
not live invocation. Runtime guard confirmations and runtime-enable
confirmations are not runtime enablement. Runtime flag target-state metadata is
not active runtime state. Guarded invocation receipt expectations and receipt
envelope readiness are not live receipts. Guarded invocation rollback
expectations, rollback readiness, and sandbox rollback manifests are not applied
rollback. Guarded invocation verification gates are not post-execution
verification, and guarded invocation audit gates are not post-execution audit.

## Decisions, candidate types, and outcomes

Supported candidate types are:

- `ai_capsule_guarded_invocation_candidate`
- `human_summary_guarded_invocation_candidate`
- `dual_capsule_guarded_invocation_candidate`
- `protect_receipt_guarded_invocation_candidate`
- `merge_receipt_guarded_invocation_candidate`
- `tomb_archive_guarded_invocation_candidate`
- `tomb_deferred_guarded_invocation_candidate`
- `operator_review_guarded_invocation_candidate`
- `noop_guarded_invocation_candidate`
- `mixed_guarded_invocation_candidate`

The implementation uses explicit `*_guarded_executor_invocation_candidate`
wire names to keep the executor boundary visible in JSON fixtures and CLI input.
Expected decisions are ready for later real executor invocation gate, ready with
warnings, deferred for operator review, rejected, blocked, or noop. Blockers
include missing or invalid guarded executor path packets, missing or invalid
candidates, non-ready guarded path decisions, digest or decision mismatches,
missing required non-noop metadata, scope mismatch, and forbidden claims.
Operator review cannot override hard blockers.

## Forbidden claims and next steps

The evaluator blocks claims that the packet enabled an executor, flipped runtime
flags, executed a live commit, invoked an executor, activated an executor,
granted permission to execute now, acquired real locks, created lockfiles,
accessed real memory roots, wrote/deleted/purged memory, mutated indexes,
persisted capsules, completed tombs, applied protection or merge operations,
assembled prompts, retrieved live context, executed actions, disclosed
externally, called external services, smuggled authority/consent/policy/truth,
or leaked raw/private/media/secret payloads.

Safe next actions are review-only: inspect the packet, resolve metadata
findings, and prepare a separate future real executor invocation gate request.
Forbidden next steps include guarded executor invocation, runtime enablement,
runtime flag flipping, live execution, executor enablement, executor invocation,
executor activation, real lock acquisition, lockfile creation, real live-memory
write/delete/purge, index mutation, prompt assembly, live context retrieval,
action ingress, sandbox bypass, real-root admission bypass, final-review bypass,
readiness-envelope bypass, runtime-gate bypass, executor-plan bypass,
lock-lease bypass, preflight bypass, activation-record bypass,
invocation-harness bypass, executor-skeleton bypass, enablement-gate bypass,
constrained-path bypass, future-execution-gate bypass,
live-commit-execution-packet bypass, runtime-enablement-packet bypass,
real-executor-runtime-gate bypass, guarded-executor-path-packet bypass, direct
executor execution, and external disclosure.

## Lifecycle

The full lifecycle remains: selective memory distillation contract, distillation
receipt gate, tomb receipt verifier, governed writer adapter, live boundary
admission gate, memory commit plan packet, operator approval packet, execution
gate, dry-run adapter, safety interlock, sandbox commit adapter, real-root
admission, final live-memory commit review, adapter readiness envelope, explicit
runtime execution gate, executor plan packet, lock lease gate, preflight packet,
activation record, invocation harness, executor skeleton, enablement gate,
constrained enablement path, future execution gate, live commit execution packet,
runtime enablement packet, real executor runtime gate, guarded executor path
packet, and then this guarded executor invocation packet. A future real executor
invocation gate remains required. Future real live-memory commit execution
remains required. Future post-execution audit remains required.

## Repository integration

Capability `guarded_executor_invocation_packet` is registered in the capability
registry with metadata-verification-only authority. The work-item review packet
matrix includes `guarded_executor_invocation_packet_tests` and targeted mypy
coverage for the module and CLI. The packet is linked from the reviewer release
readiness index as a metadata-only review surface.
