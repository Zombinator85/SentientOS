# Live Executor Invocation Harness

The live executor invocation harness is a deterministic, default-deny, metadata-only checkpoint after the [live executor activation record](live_executor_activation_record.md). It consumes supplied activation-record evidence plus explicit invocation-harness candidates and produces structured invocation-readiness, invocation-scope, operator-handoff, dry-run-equivalence, abort-readiness, rollback-readiness, and audit-readiness metadata records for a later real live-memory commit executor.

This harness is not the real live-memory commit executor, is not executor invocation, is not executor activation, and does not grant permission to execute a live commit now. Invocation readiness, activation readiness, preflight readiness, lock readiness, runtime execution gate readiness, readiness-envelope status, final-review status, real-root admission status, sandbox receipts, and sandbox rollback manifests remain evidence only.

## Boundary and non-authority posture

The harness exists so reviewers can inspect whether the evidence chain is internally aligned before any future real live-memory commit executor implementation is considered. It never activates executors, invokes executors, acquires real locks, creates or inspects lockfiles, writes real live memory, deletes memory, purges memory, mutates indexes, persists capsules or summaries, completes tombs, applies protection, applies merge operations, assembles prompts, retrieves live context, executes actions, calls external services, discloses externally, touches real memory roots, grants authority, creates policy, infers consent, or asserts truth.

Successful packets keep explicit invariants that the invocation harness is not executor invocation, not executor activation, not lock acquisition, not lockfile creation, not memory write/delete/purge, not index mutation, not capsule persistence, not tomb completion, not prompt assembly, not live context retrieval, not action execution, not external disclosure, not live commit execution, not truth, not policy, not authority, and not consent. Real executor invocation, real executor activation, real lock acquisition, lockfile creation, real-memory-root writes, live writes/deletes/purges, live index mutation, capsule persistence, tomb completion, prompt materialization, live context retrieval, action execution, external disclosure, external service use, and live executor enablement all remain disabled.

## Evidence relationships

The primary upstream dependency is the Live Executor Activation Record. An invocation candidate must match the activation-record packet digest and activation decision, and the activation decision must be ready, ready-with-warnings, or noop. Activation readiness is not live execution and execution handoff metadata is not direct executor invocation.

The harness also verifies evidence carried through the activation record:

- [Live Executor Preflight Packet](live_executor_preflight_packet.md): preflight packet digest and decision must match. Preflight readiness is not live execution or preflight execution.
- [Live Executor Lock Lease Gate](live_executor_lock_lease_gate.md): lock lease gate digest and decision must match. Lock lease readiness is not real lock acquisition and cannot create lockfiles.
- [Real Live Memory Commit Executor Plan Packet](real_live_memory_commit_executor_plan_packet.md): executor plan packet digest and decision must match. Executor plan operation records are intents only and are not executed operations.
- [Explicit Live Memory Runtime Execution Gate](explicit_live_memory_runtime_execution_gate.md): runtime execution gate digest and decision must match. Runtime execution gate readiness is not execution.
- [Real Live Memory Commit Adapter Readiness Envelope](real_live_memory_commit_adapter_readiness_envelope.md): readiness-envelope digest and decision must match. A readiness envelope is not runtime permission.
- [Final Live Memory Commit Review Gate](final_live_memory_commit_review_gate.md): final-review digest and decision must match. Final review is not execution permission.
- [Real Memory Root Admission Gate](real_memory_root_admission_gate.md): real-root admission digest and decision must match. Real-root admission is not memory-root access.
- [Sandboxed Live Memory Commit Adapter](sandboxed_live_memory_commit_adapter.md): sandbox commit digest and decision must match. Sandbox commits are not real commits, sandbox receipts are not live receipts, and sandbox rollback manifests are not applied rollback.

Scope keys must align across activation record, preflight packet, lock lease gate, executor plan, runtime execution gate, readiness envelope, final review, real-root admission, sandbox commit, and invocation-harness candidate. Operator review cannot override hard blockers.

## Candidate metadata

Supported candidate types are `ai_capsule_invocation_harness_candidate`, `human_summary_invocation_harness_candidate`, `dual_capsule_invocation_harness_candidate`, `protect_receipt_invocation_harness_candidate`, `merge_receipt_invocation_harness_candidate`, `tomb_archive_invocation_harness_candidate`, `tomb_deferred_invocation_harness_candidate`, `operator_review_invocation_harness_candidate`, `noop_invocation_harness_candidate`, and `mixed_invocation_harness_candidate`.

Non-noop candidates must include activation-readiness, operator acknowledgement, activation scope, execution handoff, final-preflight-readiness, operation inventory digest, safety checklist digest, verification checklist digest, abort-readiness, rollback-readiness, audit-readiness, lock/lease readiness, operator identity/role, execution-window, idempotency-key, atomicity-boundary, dry-run-to-live equivalence, rollback rehearsal, post-execution audit, invocation scope, invocation handoff, invocation disablement, and future executor requirement metadata. These records are metadata-only and define future review requirements; they do not activate or invoke an executor.

## Decisions, statuses, blockers, and next steps

Decisions are `invocation_harness_ready_for_later_live_executor`, `invocation_harness_ready_with_warnings`, `invocation_harness_deferred_for_operator_review`, `invocation_harness_rejected`, `invocation_harness_blocked`, and `invocation_harness_noop`. Result statuses are ready, ready with warnings, deferred for operator review, blocked, noop, invalid, or failed.

Blockers include missing or invalid activation records, missing or invalid invocation-harness candidates, non-ready activation decisions, digest or decision mismatches for activation, preflight, lock lease, executor plan, runtime gate, readiness envelope, final review, real-root admission, or sandbox commit evidence, missing non-noop metadata, scope mismatch, live write/delete/purge/index mutation claims, capsule persistence claims, tomb completion claims, protection or merge application claims, prompt materialization, live context retrieval, action execution, external disclosure, authority/consent/policy/truth smuggling, raw/private/media/secret payload leakage, lockfile creation claims, real-lock acquisition claims, executor activation claims, executor invocation claims, and claims that readiness grants permission to execute now.

Safe next actions are limited to inspection, default-deny maintenance, rerunning with corrected metadata, operator review for deferred candidates, future live executor implementation planning, and future post-execution audit planning. Forbidden next steps include executor invocation, executor activation, real lock acquisition, lockfile creation, real live-memory write/delete/purge, index mutation, prompt assembly, live context retrieval, action ingress, sandbox bypass, real-root admission bypass, final-review bypass, readiness-envelope bypass, runtime-gate bypass, executor-plan bypass, lock-lease bypass, preflight bypass, activation-record bypass, direct executor execution, and external disclosure.

## Lifecycle

The lifecycle remains evidence-only from selective memory distillation through receipt gates, governed writer readiness, boundary admission, commit planning, operator approval, execution gating, dry-run adaptation, safety interlock, sandboxed commit artifacts, real-root admission, final review, readiness envelope, runtime execution gate, executor-plan packet, lock lease gate, preflight packet, activation record, and finally this invocation harness. A future real live-memory commit executor remains required, a future live executor implementation remains required, and a future post-execution audit remains required.

## CLI and fixtures

`scripts/build_live_executor_invocation_harness.py` supports `build-default`, `evaluate`, `validate`, `summarize`, and `inspect-fixture`. `evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or failed outcomes exit nonzero. Fixtures live under `tests/fixtures/live_executor_invocation_harness/`. The capability is registered as `live_executor_invocation_harness`, linked from the reviewer release readiness index, and covered by the work-item review packet matrix lane `live_executor_invocation_harness_tests`.
