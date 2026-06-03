# Real Executor Runtime Gate

The real executor runtime gate is a deterministic, metadata-only review gate
that follows the [Real Executor Runtime Enablement Packet](real_executor_runtime_enablement_packet.md).
It exists to decide whether a later guarded real executor path may be considered
from supplied evidence, while keeping the runtime default-deny and disabled. It
is not real live-memory commit execution, not executor runtime enablement, not a
runtime flag flip, not an enabled live-memory commit executor, and not executor
activation or invocation.

## Upstream evidence relationships

The primary dependency is the real executor runtime enablement packet. A runtime
gate candidate must claim the exact runtime enablement packet digest and decision
present in the supplied packet. Runtime enablement packet readiness is only
metadata and is not permission to flip runtime flags.

The gate also rechecks every digest and decision carried forward by upstream
memory-chain packets:

- [Live Commit Execution Packet](live_commit_execution_packet.md): packet digest
  and decision must match. Live commit execution packet readiness is not
  permission to execute.
- [Future Live Memory Commit Execution Gate](future_live_memory_commit_execution_gate.md):
  future execution gate digest and decision must match. Future execution gate
  readiness is not permission to execute.
- [Constrained Executor Enablement Path Packet](constrained_executor_enablement_path_packet.md):
  constrained path digest and decision must match. Constrained path readiness is
  not executor enablement.
- [Real Live Memory Commit Executor Enablement Gate](real_live_memory_commit_executor_enablement_gate.md):
  executor enablement gate digest and decision must match. Enablement gate
  readiness is not runtime enablement.
- [Real Live Memory Commit Executor Implementation Skeleton](real_live_memory_commit_executor_implementation_skeleton.md):
  executor skeleton digest and decision must match. Executor skeleton records are
  disabled API/envelope metadata only, not executed operations.
- [Live Executor Invocation Harness](live_executor_invocation_harness.md):
  invocation harness digest and decision must match. Invocation readiness is not
  live execution.
- [Live Executor Activation Record](live_executor_activation_record.md):
  activation digest and decision must match. Activation readiness is not live
  execution.
- [Live Executor Preflight Packet](live_executor_preflight_packet.md): preflight
  digest and decision must match. Preflight readiness is not live execution.
- [Live Executor Lock Lease Gate](live_executor_lock_lease_gate.md): lock lease
  digest and decision must match. Lock lease readiness is not real lock
  acquisition, does not inspect real lockfiles, and does not create lockfiles.
- [Real Live Memory Commit Executor Plan Packet](real_live_memory_commit_executor_plan_packet.md):
  executor plan digest and decision must match. Executor plan operation records
  are intents only, not executed operations.
- [Explicit Live Memory Runtime Execution Gate](explicit_live_memory_runtime_execution_gate.md):
  runtime execution gate digest and decision must match. Runtime execution gate
  readiness is not execution.
- [Real Live Memory Commit Adapter Readiness Envelope](real_live_memory_commit_adapter_readiness_envelope.md):
  readiness-envelope digest and decision must match. A readiness envelope is not
  runtime permission.
- [Final Live Memory Commit Review Gate](final_live_memory_commit_review_gate.md):
  final-review digest and decision must match. Final review is not execution
  permission.
- [Real Memory Root Admission Gate](real_memory_root_admission_gate.md):
  real-root admission digest and decision must match. Real-root admission is not
  memory-root access.
- [Sandboxed Live Memory Commit Adapter](sandboxed_live_memory_commit_adapter.md):
  sandbox commit digest and decision must match. Sandbox commits are not real
  commits, sandbox receipts are not live receipts, and sandbox rollback manifests
  are not applied rollback.

The gate remains downstream of the live commit safety interlock, live memory
commit dry-run adapter, memory commit execution gate, memory commit operator
approval packet, memory commit plan packet, live memory boundary admission gate,
governed memory writer adapter, selective memory tomb receipt verifier,
selective memory distillation receipt gate, and selective memory distillation
contract. It does not bypass those layers.

## Boundary and non-authority posture

The gate is default-deny and metadata-only. It does not enable, activate, or
invoke an executor. It does not flip runtime flags. It does not execute a live
commit. It does not acquire locks, create lockfiles, inspect real lockfiles,
write, delete, purge, mutate indexes, persist capsules or summaries, apply
protection or merge operations, complete tombs, assemble prompts, retrieve live
context, execute actions, call external services, disclose externally, assert
truth, create policy, infer consent, or grant authority. It does not read or
write real memory roots.

Runtime-gate readiness, runtime-enable confirmation, runtime-flag confirmation,
guarded-executor-path prerequisites, emergency-stop confirmation, rollback
readiness, verification readiness, audit readiness, idempotency keys, atomicity
boundaries, execution windows, operator identity/role metadata, clean-tree
expectations, and scope alignment are metadata-only records. Runtime flag
confirmation is not active runtime state. Guarded executor path prerequisites are
not executor invocation. Operation bundle records and executor plan records are
intents only. Receipt envelope readiness is not a live receipt. Rollback
readiness is not applied rollback. Verification readiness is not post-execution
verification.

Future guarded executor path review remains required. Future real live-memory
commit execution remains required. Future post-execution audit remains required.
No operator review can override hard blockers.

## Candidates, decisions, blockers, and next actions

Candidate types are:

- `ai_capsule_runtime_gate_candidate`
- `human_summary_runtime_gate_candidate`
- `dual_capsule_runtime_gate_candidate`
- `protect_receipt_runtime_gate_candidate`
- `merge_receipt_runtime_gate_candidate`
- `tomb_archive_runtime_gate_candidate`
- `tomb_deferred_runtime_gate_candidate`
- `operator_review_runtime_gate_candidate`
- `noop_runtime_gate_candidate`
- `mixed_runtime_gate_candidate`

Decisions are:

- `runtime_gate_ready_for_later_guarded_executor_path`
- `runtime_gate_ready_with_warnings`
- `runtime_gate_deferred_for_operator_review`
- `runtime_gate_rejected`
- `runtime_gate_blocked`
- `runtime_gate_noop`

Hard blockers include missing or invalid runtime enablement packet evidence,
missing or invalid candidates, non-ready upstream runtime enablement packet
decisions, digest or decision mismatches for any upstream evidence, missing
non-noop metadata, scope mismatch, live write/delete/purge/index mutation claims,
capsule persistence claims, tomb completion claims, protection or merge
application claims, prompt materialization, live context retrieval, action
execution, external disclosure, authority/consent/policy/truth smuggling, raw or
private/media/secret payload leakage, lockfile creation claims, real-lock
acquisition claims, executor enablement claims, runtime-flag flipping claims,
executor activation or invocation claims, and live execution claims.

Safe next actions are review-only: inspect the runtime gate packet, resolve
operator review metadata where requested, or prepare a separate future guarded
executor path request. Forbidden next steps include runtime enablement, runtime
flag flipping, guarded executor invocation, live execution, executor enablement,
executor invocation, executor activation, real lock acquisition, lockfile
creation, real live-memory write/delete/purge, index mutation, prompt assembly,
live context retrieval, action ingress, sandbox bypass, real-root admission
bypass, final-review bypass, readiness-envelope bypass, runtime-gate bypass,
executor-plan bypass, lock-lease bypass, preflight bypass, activation-record
bypass, invocation-harness bypass, executor-skeleton bypass, enablement-gate
bypass, constrained-path bypass, future-execution-gate bypass,
live-commit-execution-packet bypass, runtime-enablement-packet bypass, direct
executor execution, and external disclosure.

## Lifecycle

The lifecycle begins with selective memory distillation contract evidence, then
passes through receipt gates, tomb verification, governed writer admission,
boundary admission, commit planning, operator approval, execution gates, dry-run
and safety interlock evidence, sandboxed commit artifacts, real-root admission,
final review, readiness envelope, runtime execution gate, executor plan, lock
lease, preflight, activation, invocation, executor skeleton, executor enablement
gate, constrained enablement path, future execution gate, live commit execution
packet, real executor runtime enablement packet, and finally this real executor
runtime gate. Each layer carries metadata forward; none of those records become
live memory mutation or runtime authority merely because this gate verifies them.

## Repository integration

`sentientos/real_executor_runtime_gate.py` exposes the pure evaluator.
`scripts/build_real_executor_runtime_gate.py` supports `build-default`,
`evaluate`, `validate`, `summarize`, and `inspect-fixture`. Fixtures live under
`tests/fixtures/real_executor_runtime_gate/`. The capability is registered as
`real_executor_runtime_gate`, linked from the context hygiene spine and reviewer
release readiness index, represented in the reviewer proof bundle as
`real_executor_runtime_gate_capability.json`, and covered by the work-item review
packet matrix lane `real_executor_runtime_gate_tests`.
