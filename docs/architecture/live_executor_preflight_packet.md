# Live Executor Preflight Packet

The live executor preflight packet is a deterministic, default-deny, metadata-only checkpoint after the [live executor lock lease gate](live_executor_lock_lease_gate.md). It consumes supplied lock-lease gate evidence plus explicit preflight candidates and produces a final reviewable packet for a later real live-memory commit executor. It is not the real live-memory commit executor and it is not real preflight execution.

## Boundary

The packet exists so reviewers can inspect final preflight readiness, operation inventory, safety checklist, verification checklist, abort readiness, rollback readiness, audit readiness, lock/lease readiness, clean-tree expectations, contamination checks, generated-artifact cleanup expectations, idempotency keys, atomicity boundaries, execution windows, and operator identity/role metadata before any future real live-memory commit executor is implemented or activated.

It never performs real preflight execution, acquires a real lock, creates or inspects lockfiles, writes real live memory, deletes memory, purges memory, mutates indexes, persists capsules or summaries, completes tombs, applies protection, applies merge operations, assembles prompts, retrieves live context, executes actions, invokes remote services, discloses externally, touches real memory roots, grants authority, creates policy, infers consent, or asserts truth. Final-preflight-readiness, operation-inventory, safety-checklist, verification-checklist, abort-readiness, rollback-readiness, and audit-readiness records are metadata-only review records.

Successful packets keep the safety invariants explicit: lock acquisition is not performed, lockfile creation is disabled, real memory-root writes are disabled, live writes/deletes/purges are disabled, index mutation is disabled, capsule persistence and tomb completion are disabled, prompt materialization and live context retrieval are disabled, action execution and external disclosure are disabled, remote services are disabled, and the live executor remains disabled. Operation inventory records are intents only; receipt targets and rollback targets are metadata only.

## Upstream evidence relationship

The primary upstream dependency is the live executor lock lease gate. A preflight candidate must match the lock lease gate packet digest and lock lease gate decision, and the lock lease gate decision must be ready, ready-with-warnings, or noop. Lock lease readiness is not real lock acquisition, and lease readiness is not permission to create lockfiles.

The packet also repeats and verifies evidence carried through the lock lease gate record:

- [Real live memory commit executor plan packet](real_live_memory_commit_executor_plan_packet.md): executor plan packet digest and decision must match. Executor plan operation records remain intents only and are not executed operations.
- [Explicit live memory runtime execution gate](explicit_live_memory_runtime_execution_gate.md): runtime execution gate digest and decision must match, but runtime execution gate readiness is not execution.
- [Real live memory commit adapter readiness envelope](real_live_memory_commit_adapter_readiness_envelope.md): readiness-envelope digest and decision must match, but a readiness envelope is not runtime permission.
- [Final live memory commit review gate](final_live_memory_commit_review_gate.md): final-review digest and decision must match, but final review is not execution permission.
- [Real memory root admission gate](real_memory_root_admission_gate.md): real-root admission digest and decision must match, but real-root admission is not memory-root access.
- [Sandboxed live memory commit adapter](sandboxed_live_memory_commit_adapter.md): sandbox commit digest and decision must match, but sandbox commits are not real commits, sandbox receipts are not live receipts, and sandbox rollback manifests are not applied rollback.

Scope keys must align across the lock lease gate, executor plan, runtime execution gate, readiness envelope, final review, real-root admission, sandbox commit, and preflight candidate. Mixed diagnostic packets may warn only when policy explicitly allows them. Operator review cannot override hard blockers.

## Candidate metadata

Supported candidate types are `ai_capsule_preflight_candidate`, `human_summary_preflight_candidate`, `dual_capsule_preflight_candidate`, `protect_receipt_preflight_candidate`, `merge_receipt_preflight_candidate`, `tomb_archive_preflight_candidate`, `tomb_deferred_preflight_candidate`, `operator_review_preflight_candidate`, `noop_preflight_candidate`, and `mixed_preflight_candidate`.

Non-noop candidates must provide operation-list digest metadata, operation inventory metadata, operation ordering metadata, per-operation precondition metadata, per-operation receipt target metadata, per-operation rollback target metadata, lock/lease readiness metadata, lease duration metadata, lock owner metadata, operator identity/role metadata, execution-window metadata, idempotency-key metadata, atomicity boundary metadata, dry-run-to-live equivalence metadata, rollback rehearsal metadata, post-execution audit metadata, verification checklist metadata, abort/panic/stop-condition metadata, contamination check metadata, generated-artifact cleanup expectation metadata, final clean-tree expectation metadata, and explicit future executor requirement metadata. These fields describe what a future executor must prove later; they do not execute operations, acquire locks, create lockfiles, write memory, or apply rollback.

## Decisions, statuses, blockers, and next steps

Decisions are `preflight_ready_for_later_live_executor`, `preflight_ready_with_warnings`, `preflight_deferred_for_operator_review`, `preflight_rejected`, `preflight_blocked`, and `preflight_noop`. Result statuses are ready, ready with warnings, deferred for operator review, rejected, blocked, noop, invalid, or failed.

Blockers include missing or invalid lock lease gate packets, missing or invalid preflight candidates, non-ready lock lease gate decisions, digest or decision mismatches for lock lease gate, executor plan, runtime execution gate, readiness envelope, final review, real-root admission, or sandbox commit evidence, missing required non-noop metadata, scope mismatch, preflight execution claims, real-lock acquisition claims, lockfile creation claims, live write/delete/purge/index mutation claims, capsule persistence claims, tomb completion claims, protection or merge application claims, prompt materialization, live context retrieval, action execution, external disclosure, authority/consent/policy/truth smuggling, raw/private/media/secret payload leakage, and any claim that this packet grants permission to execute a live commit now.

Safe next actions are inspection, sustaining default-deny posture, rerunning with corrected metadata, operator review where applicable, preparing a future real live-memory commit executor later, preparing a future executor activation record later, and preparing a future post-execution audit later. Forbidden next steps include real lock acquisition, lockfile creation, real live-memory write/delete/purge, index mutation, prompt assembly, live context retrieval, action ingress, sandbox bypass, real-root admission bypass, final-review bypass, readiness-envelope bypass, runtime-gate bypass, executor-plan bypass, lock-lease bypass, direct executor invocation, and external disclosure.

## Lifecycle

The lifecycle remains evidence-only from selective memory distillation through receipt verification, governed writer readiness, boundary admission, commit planning, operator approval, execution gating, dry-run adaptation, safety interlock, sandboxed commit artifacts, real-root admission, final review, readiness envelope, runtime execution gate, executor-plan packet, lock lease gate, and finally this preflight packet. This preflight packet is the last deterministic review packet before a later real executor can be designed, but that future real live-memory commit executor remains required, a future executor activation record remains required, and a future post-execution audit remains required.

## CLI, fixtures, and integration

`scripts/build_live_executor_preflight_packet.py` supports `build-default`, `evaluate`, `validate`, `summarize`, and `inspect-fixture`. `evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or failed outcomes exit nonzero.

Fixtures live under `tests/fixtures/live_executor_preflight_packet/`. The capability is registered as `live_executor_preflight_packet`, linked from the context hygiene spine and reviewer release readiness index, and covered by the work-item review packet matrix lane `live_executor_preflight_packet_tests`.
