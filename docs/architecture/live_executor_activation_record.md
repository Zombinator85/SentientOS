# Live Executor Activation Record

The live executor activation record is a deterministic, default-deny, metadata-only checkpoint after the [live executor preflight packet](live_executor_preflight_packet.md). It consumes supplied preflight packet evidence plus explicit activation candidates and produces structured activation-readiness records for a later real live-memory commit executor. It is not the real live-memory commit executor, does not activate a live executor, and does not grant permission to execute a live commit now.

## Boundary

The record exists so reviewers can inspect activation readiness, operator activation acknowledgement, activation scope, execution handoff, abort readiness, rollback readiness, audit readiness, final-preflight readiness, operation inventory digests, safety checklist digests, verification checklist digests, lock/lease readiness, execution windows, idempotency keys, atomicity boundaries, dry-run-to-live equivalence, rollback rehearsal, post-execution audit expectations, operator identity/role metadata, future executor requirements, clean-tree expectations carried from preflight evidence, and scope alignment before any future live executor invocation harness or real live-memory commit executor is implemented.

It never activates an executor, acquires a real lock, creates or inspects lockfiles, writes real live memory, deletes memory, purges memory, mutates indexes, persists capsules or summaries, completes tombs, applies protection, applies merge operations, assembles prompts, retrieves live context, executes actions, invokes remote services, discloses externally, touches real memory roots, grants authority, creates policy, infers consent, or asserts truth. Activation-readiness, operator-acknowledgement, activation-scope, execution-handoff, abort-readiness, rollback-readiness, and audit-readiness records are metadata-only review records.

Successful records keep explicit invariants: activation is not executor activation; lock readiness is not lock acquisition; lockfile creation is disabled; real memory-root writes are disabled; live writes/deletes/purges are disabled; index mutation is disabled; capsule persistence and tomb completion are disabled; prompt materialization and live context retrieval are disabled; action execution and external disclosure are disabled; remote services are disabled; and the live executor remains disabled. Activation readiness is not live execution, operator acknowledgement is not consent to bypass later gates, activation scope is not memory-root access, and execution handoff is not direct executor invocation.

## Upstream evidence relationship

The primary upstream dependency is the Live Executor Preflight Packet. An activation candidate must match the preflight packet digest and preflight decision, and the preflight decision must be ready, ready-with-warnings, or noop. Preflight readiness is not live execution and does not perform preflight execution.

The activation record also verifies evidence carried through the preflight packet:

- [Live Executor Lock Lease Gate](live_executor_lock_lease_gate.md): lock lease gate digest and decision must match. Lock lease readiness is not real lock acquisition and does not create lockfiles.
- [Real Live Memory Commit Executor Plan Packet](real_live_memory_commit_executor_plan_packet.md): executor plan packet digest and decision must match. Executor plan operation records are intents only and are not executed operations.
- [Explicit Live Memory Runtime Execution Gate](explicit_live_memory_runtime_execution_gate.md): runtime execution gate digest and decision must match. Runtime execution gate readiness is not execution.
- [Real Live Memory Commit Adapter Readiness Envelope](real_live_memory_commit_adapter_readiness_envelope.md): readiness-envelope digest and decision must match. A readiness envelope is not runtime permission.
- [Final Live Memory Commit Review Gate](final_live_memory_commit_review_gate.md): final-review digest and decision must match. Final review is not execution permission.
- [Real Memory Root Admission Gate](real_memory_root_admission_gate.md): real-root admission digest and decision must match. Real-root admission is not memory-root access.
- [Sandboxed Live Memory Commit Adapter](sandboxed_live_memory_commit_adapter.md): sandbox commit digest and decision must match. Sandbox commits are not real commits, sandbox receipts are not live receipts, and sandbox rollback manifests are not applied rollback.

Scope keys must align across the preflight packet, lock lease gate, executor plan, runtime execution gate, readiness envelope, final review, real-root admission, sandbox commit, and activation candidate. Mixed diagnostic records may warn only when policy explicitly allows them. Operator review cannot override hard blockers.

## Candidate metadata

Supported candidate types are `ai_capsule_activation_candidate`, `human_summary_activation_candidate`, `dual_capsule_activation_candidate`, `protect_receipt_activation_candidate`, `merge_receipt_activation_candidate`, `tomb_archive_activation_candidate`, `tomb_deferred_activation_candidate`, `operator_review_activation_candidate`, `noop_activation_candidate`, and `mixed_activation_candidate`.

Non-noop candidates must provide final-preflight-readiness metadata, operation-inventory digest metadata, safety-checklist digest metadata, verification-checklist digest metadata, abort-readiness metadata, rollback-readiness metadata, audit-readiness metadata, lock/lease readiness metadata, operator identity/role metadata, operator activation acknowledgement metadata, execution-window metadata, idempotency-key metadata, atomicity-boundary metadata, dry-run-to-live equivalence metadata, rollback rehearsal metadata, post-execution audit metadata, activation-scope metadata, execution-handoff metadata, and future-executor requirement metadata. These fields describe what a later executor and invocation harness must prove later; they do not activate the executor, acquire locks, create lockfiles, write memory, or apply rollback.

## Decisions, statuses, blockers, and next steps

Decisions are `activation_record_ready_for_later_live_executor`, `activation_record_ready_with_warnings`, `activation_record_deferred_for_operator_review`, `activation_record_rejected`, `activation_record_blocked`, and `activation_record_noop`. Result statuses are ready, ready with warnings, deferred for operator review, blocked, invalid, failed, and noop.

Hard blockers include missing or invalid preflight packets, missing or invalid activation candidates, non-ready preflight decisions, digest mismatches, decision mismatches, missing non-noop metadata, live write/delete/purge/index mutation claims, capsule persistence claims, tomb completion claims, protection or merge application claims, prompt materialization claims, live context retrieval claims, action execution claims, external disclosure claims, authority/consent/policy/truth smuggling, raw/private/media/secret payload leakage, lockfile creation claims, real-lock acquisition claims, executor activation claims, real-memory-root access claims, executor permission claims, and scope mismatch. Operator review cannot override these hard blockers.

Safe next actions are reviewer-only: inspect the activation record, repair metadata, rerun upstream packet generation if evidence changed, design a future live executor invocation harness later, and plan a future post-execution audit. Forbidden next steps include executor activation, real lock acquisition, lockfile creation, real live-memory write/delete/purge, index mutation, prompt assembly, live context retrieval, action ingress, sandbox bypass, real-root admission bypass, final-review bypass, readiness-envelope bypass, runtime-gate bypass, executor-plan bypass, lock-lease bypass, preflight bypass, direct executor invocation, and external disclosure.

## Lifecycle

The lifecycle remains metadata-only from distillation through activation record: selective distillation contracts create retain/distill/tomb intent metadata; receipt gates and tomb verifiers check receipt evidence; governed writer and boundary gates produce local artifact/admission metadata; memory commit plans, operator approval packets, execution gates, dry-run adapters, safety interlocks, sandbox commits, real-root admission, final review, readiness envelopes, runtime execution gates, executor plan packets, lock lease gates, and preflight packets progressively narrow evidence. The activation record consumes that evidence and creates deterministic activation-readiness metadata for future review only.

A future real live-memory commit executor remains required. A future live executor invocation harness remains required. A future post-execution audit remains required. This record deliberately stops before all three.
