# SentientOS Explicit Live Memory Runtime Execution Gate

The explicit live memory runtime execution gate is a deterministic, default-deny, metadata-only checkpoint after the [real live memory commit adapter readiness envelope](real_live_memory_commit_adapter_readiness_envelope.md). It consumes supplied readiness-envelope packets and explicit runtime execution gate candidates to decide only whether a later real live-memory commit executor may be considered.

This gate is not the real live memory commit executor. It does not write, delete, purge, index, persist, apply, merge, complete tombs, assemble prompts, retrieve live context, execute actions, disclose externally, invoke remote services, touch real memory roots, create truth, create policy, infer consent, or grant authority.

## Why the runtime execution gate exists

The readiness envelope can show that final review, real-root admission, sandbox commit, sandbox receipt, rollback, artifact-plan, abort, and post-commit verification metadata are internally consistent. That still cannot execute a real live-memory commit. The explicit runtime execution gate adds a later membrane that verifies explicit operator runtime confirmation candidates, operator identity and role metadata, execution-window metadata, dry-run-to-live equivalence metadata, rollback rehearsal metadata, and post-execution audit metadata while keeping every live effect disabled.

A ready runtime execution gate packet means only that supplied metadata is consistent enough for a future real live-memory commit executor to be considered later. It is not permission to execute now, not runtime execution, not a live commit, not a live receipt, not applied rollback, and not access to a real memory root.

## Relationship to upstream membranes

- **Real Live Memory Commit Adapter Readiness Envelope:** the primary upstream dependency. Candidates must claim the supplied readiness-envelope digest and readiness decision, and those claims must match the supplied readiness record.
- **Final Live Memory Commit Review Gate:** runtime candidates must also match the final-review digest and decision carried by the readiness envelope. Final review is not execution permission and cannot be converted into a real commit.
- **Real Memory Root Admission Gate:** runtime candidates must match the real-root admission digest and decision carried by the readiness envelope. Real-root admission remains metadata and is not memory-root access.
- **Sandboxed Live Memory Commit Adapter:** runtime candidates must match the sandbox commit digest and decision carried by the readiness envelope. Sandbox commits are not real commits, sandbox receipts are not live receipts, and sandbox rollback manifests are not applied rollback.
- **Earlier memory-chain membranes:** the lifecycle remains chained through the Selective Memory Distillation Contract, Selective Memory Distillation Receipt Gate, Selective Memory Tomb Receipt Verifier, Governed Memory Writer Adapter, Live Memory Boundary Admission Gate, Memory Commit Plan Packet, Memory Commit Operator Approval Packet, Memory Commit Execution Gate, Live Memory Commit Dry-Run Adapter, Live Commit Safety Interlock, Sandboxed Live Memory Commit Adapter, Real Memory Root Admission Gate, Final Live Memory Commit Review Gate, Real Live Memory Commit Adapter Readiness Envelope, and then this gate.

## Required non-noop metadata

Every non-noop runtime execution gate candidate must include matching readiness-envelope digest and decision evidence, matching final-review digest and decision evidence, matching real-root admission digest and decision evidence, matching sandbox commit digest and decision evidence, sandbox receipt manifest digest, sandbox rollback manifest digest, sandbox artifact-plan evidence, live receipt schema metadata, live rollback schema metadata, post-commit verification plan metadata, abort/panic/stop-condition metadata, explicit operator runtime confirmation metadata, explicit operator identity and role metadata, execution-window metadata, dry-run-to-live equivalence metadata, rollback-rehearsal metadata, post-execution audit metadata, and scope alignment across the readiness envelope, final review, real-root admission, sandbox commit, and runtime execution candidate.

The emitted execution-precondition record is metadata only. The emitted verification-readiness record is metadata only. The emitted abort-readiness record is metadata only. The emitted rollback-readiness record is metadata only. None of these records write memory, execute the commit, emit live receipts, apply rollback, or create authority.

## Candidate types

- `ai_capsule_runtime_execution_gate_candidate`
- `human_summary_runtime_execution_gate_candidate`
- `dual_capsule_runtime_execution_gate_candidate`
- `protect_receipt_runtime_execution_gate_candidate`
- `merge_receipt_runtime_execution_gate_candidate`
- `tomb_archive_runtime_execution_gate_candidate`
- `tomb_deferred_runtime_execution_gate_candidate`
- `operator_review_runtime_execution_gate_candidate`
- `noop_runtime_execution_gate_candidate`
- `mixed_runtime_execution_gate_candidate`

## Decisions, statuses, blockers, and actions

Candidate decisions are `runtime_execution_gate_ready_for_later_live_executor`, `runtime_execution_gate_ready_with_warnings`, `runtime_execution_gate_deferred_for_operator_review`, `runtime_execution_gate_rejected`, `runtime_execution_gate_blocked`, and `runtime_execution_gate_noop`.

Result statuses are `runtime_execution_gate_ready`, `runtime_execution_gate_ready_with_warnings`, `runtime_execution_gate_deferred_for_operator_review`, `runtime_execution_gate_rejected`, `runtime_execution_gate_blocked`, `runtime_execution_gate_noop`, `runtime_execution_gate_invalid`, and `runtime_execution_gate_failed`.

Hard blockers include missing or invalid readiness-envelope packets, missing or invalid runtime execution gate candidates, readiness-envelope not-ready evidence, readiness-envelope digest mismatch, readiness-envelope decision mismatch, final-review digest mismatch, final-review decision mismatch, real-root admission digest mismatch, real-root admission decision mismatch, sandbox commit digest mismatch, sandbox commit decision mismatch, missing sandbox receipt manifest digest, missing sandbox rollback manifest digest, missing sandbox artifact plan, missing live receipt schema metadata, missing live rollback schema metadata, missing post-commit verification plan, missing abort/panic/stop-condition metadata, missing operator runtime confirmation metadata, missing operator identity/role metadata, missing execution-window metadata, missing dry-run-to-live equivalence metadata, missing rollback-rehearsal metadata, missing post-execution audit metadata, live write/delete/purge/index mutation claims, capsule persistence claims, tomb completion claims, protection or merge application claims, prompt materialization, live context retrieval, action execution, external disclosure, authority smuggling, consent smuggling, policy smuggling, truth smuggling, raw/private/media/secret payload leakage, and scope mismatch. Operator review cannot override hard blockers.

Safe next actions are limited to packet inspection, operator review, preparing a future executor later, preparing future operator runtime confirmation later, preparing future post-execution audit later, rerunning with corrected metadata, and sustaining default deny. Forbidden next steps include real live-memory write/delete/purge, index mutation, prompt assembly, live context retrieval, action ingress, sandbox bypass, real-root admission bypass, final-review bypass, readiness-envelope bypass, direct executor invocation, and external disclosure.

## CLI, fixtures, and repository integration

`scripts/build_explicit_live_memory_runtime_execution_gate.py` supports `build-default`, `evaluate`, `validate`, `summarize`, and `inspect-fixture`. `evaluate` emits deterministic JSON and writes nothing. Blocked, invalid, or failed outcomes exit nonzero.

Fixtures live under `tests/fixtures/explicit_live_memory_runtime_execution_gate/`. The capability is registered as `explicit_live_memory_runtime_execution_gate`, appears in the reviewer proof bundle, is linked from the context hygiene spine, and is covered by the work-item review packet matrix lane `explicit_live_memory_runtime_execution_gate_tests`.
