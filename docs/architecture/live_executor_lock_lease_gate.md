# Live Executor Lock Lease Gate

The live executor lock lease gate is a deterministic, default-deny, metadata-only checkpoint after the [real live memory commit executor plan packet](real_live_memory_commit_executor_plan_packet.md). It consumes supplied executor-plan packet evidence plus explicit lock-lease candidates and decides only whether a later real live-memory commit executor may be considered with lock and lease prerequisites documented. It is not the real live-memory commit executor, is not a live executor preflight, and is not permission to execute a live commit now.

## Boundary

The gate exists so reviewers can inspect lock-readiness, lease-readiness, contention, timeout, stale-lease, abort, rollback, and post-execution audit metadata before any future live executor is implemented. The gate never acquires a real lock, creates or inspects lockfiles, writes real live memory, deletes memory, purges memory, mutates indexes, persists capsules or summaries, completes tombs, applies protection, applies merge operations, assembles prompts, retrieves live context, executes actions, invokes remote services, discloses externally, touches real memory roots, grants authority, creates policy, infers consent, or asserts truth.

Successful packets keep these invariants true: lock acquisition is not performed, lockfile creation is disabled, real memory-root writes are disabled, live memory writes/deletes/purges are disabled, index mutation is disabled, capsule persistence and tomb completion are disabled, prompt materialization and live context retrieval are disabled, action execution and external disclosure are disabled, remote services are disabled, and the live executor remains disabled. Lock-readiness and lease-readiness are metadata-only records; contention, timeout, stale-lease, abort-readiness, rollback-readiness, and audit-readiness records are also metadata-only.

## Upstream evidence relationship

The primary upstream dependency is the real live-memory commit executor plan packet. Candidates must match the executor-plan packet digest and executor-plan decision. The executor-plan operation records are intents only; this gate does not treat those intents as executed operations.

The candidate also repeats and matches evidence carried by the executor-plan record:

- [Explicit live memory runtime execution gate](explicit_live_memory_runtime_execution_gate.md): runtime gate digest and decision must match, but runtime gate readiness is not execution.
- [Real live memory commit adapter readiness envelope](real_live_memory_commit_adapter_readiness_envelope.md): readiness-envelope digest and decision must match, but the readiness envelope is not runtime permission.
- [Final live memory commit review gate](final_live_memory_commit_review_gate.md): final-review digest and decision must match, but final review is not execution permission.
- [Real memory root admission gate](real_memory_root_admission_gate.md): real-root admission digest and decision must match, but real-root admission is not memory-root access.
- [Sandboxed live memory commit adapter](sandboxed_live_memory_commit_adapter.md): sandbox commit digest and decision must match, but sandbox commits are not real commits, sandbox receipts are not live receipts, and sandbox rollback manifests are not applied rollback.

Scope keys must align across the executor plan, runtime execution gate, readiness envelope, final review, real-root admission, sandbox commit, and lock-lease candidate. Mixed diagnostic packets may warn only when policy explicitly allows them. Operator review cannot override hard blockers.

## Candidate metadata

Supported candidate types are `ai_capsule_lock_lease_candidate`, `human_summary_lock_lease_candidate`, `dual_capsule_lock_lease_candidate`, `protect_receipt_lock_lease_candidate`, `merge_receipt_lock_lease_candidate`, `tomb_archive_lock_lease_candidate`, `tomb_deferred_lock_lease_candidate`, `operator_review_lock_lease_candidate`, `noop_lock_lease_candidate`, and `mixed_lock_lease_candidate`.

Non-noop candidates must provide operation-list digest metadata, lock/lease expectation metadata, lease duration metadata, lock owner metadata, operator identity/role metadata, execution-window metadata, idempotency-key metadata, atomicity boundary metadata, contention policy metadata, stale-lease policy metadata, timeout policy metadata, abort-condition metadata, rollback-target metadata, and post-execution audit metadata. These fields describe what a future executor must prove later; they do not acquire locks, create lockfiles, execute operations, write memory, or apply rollback.

## Decisions, statuses, and blockers

Decisions are `lock_lease_ready_for_later_live_executor`, `lock_lease_ready_with_warnings`, `lock_lease_deferred_for_operator_review`, `lock_lease_rejected`, `lock_lease_blocked`, and `lock_lease_noop`. Result statuses are ready, ready with warnings, deferred for operator review, rejected, blocked, noop, invalid, or failed.

Blockers include missing or invalid executor-plan packets, missing or invalid lock-lease candidates, non-ready executor-plan decisions, digest or decision mismatches, missing required non-noop metadata, scope mismatch, real-lock acquisition claims, lockfile creation claims, live write/delete/purge/index mutation claims, capsule persistence claims, tomb completion claims, protection or merge application claims, prompt materialization, live context retrieval, action execution, external disclosure, authority/consent/policy/truth smuggling, raw/private/media/secret payload leakage, and any claim that this gate grants permission to execute a live commit now.

Safe next actions are inspection, sustaining default-deny posture, rerunning with corrected metadata, operator review where applicable, preparing a future real live-memory commit executor later, preparing future live executor preflight later, and preparing future post-execution audit later. Forbidden next steps are real lock acquisition, lockfile creation, real live-memory write/delete/purge, index mutation, prompt assembly, live context retrieval, action ingress, sandbox bypass, real-root admission bypass, final-review bypass, readiness-envelope bypass, runtime-gate bypass, executor-plan bypass, direct executor invocation, and external disclosure.

## Lifecycle

The memory chain remains staged: selective memory distillation defines metadata-only retention/capsule/tomb intent; receipt and tomb gates verify metadata; governed writer and boundary gates prepare review-only artifacts; commit plan, operator approval, execution gate, dry run, interlock, sandbox commit, real-root admission, final review, readiness envelope, runtime execution gate, and executor-plan packet each add deterministic evidence without granting live authority. This lock lease gate is the next metadata-only checkpoint after the executor-plan packet. A future real live-memory commit executor remains required, a future live executor preflight remains required, and a future post-execution audit remains required.
