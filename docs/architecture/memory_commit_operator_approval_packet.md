# Memory Commit Operator Approval Packet

The memory commit operator approval packet is a deterministic, metadata-only review layer after the [memory commit plan packet](memory_commit_plan_packet.md). It converts supplied commit-plan evidence and explicit operator approval-candidate metadata into reviewable approval, warning, deferral, rejection, or blocked records for later consideration.

It never executes a plan. It never writes live memory, deletes memory, mutates vector indexes, persists capsules, applies protections, applies merges, completes tombs, assembles prompts, retrieves live context, executes actions, invokes remote services, discloses externally, creates policy, proves truth, grants consent, or grants authority.

## Position in the memory chain

The packet sits after the existing memory digestion/output/boundary/plan chain:

1. [Selective memory distillation contract](selective_memory_distillation_contract.md)
2. [Selective memory distillation receipt gate](selective_memory_distillation_receipt_gate.md)
3. [Selective memory tomb receipt verifier](selective_memory_tomb_receipt_verifier.md)
4. [Governed memory writer adapter](governed_memory_writer_adapter.md)
5. [Live memory boundary admission gate](live_memory_boundary_admission_gate.md)
6. [Memory commit plan packet](memory_commit_plan_packet.md)
7. Memory commit operator approval packet
8. Future memory commit execution gate
9. Future live memory commit adapter only after explicit later admission
10. Self-improvement perception and affective ingress ledger
11. GenesisForge embodied self-improvement handoff packet

The commit plan packet remains plan-only. The operator approval packet is approval-only and future-consideration-only. A future execution gate and future live commit adapter are still required before any live memory effect can be considered.

## Why approval is not an effect

Approval metadata is not memory writing because it only records whether supplied plan evidence is eligible for later review. It does not call memory append, purge, curation, summarization, tomb completion, merge, protection, or index mutation surfaces.

Approval metadata is not deletion because it cannot complete tombs, purge memory, prove deletion, or remove records. Tomb-related candidates remain receipt expectations for later schemas.

Approval metadata is not capsule persistence because candidate approval does not store capsules or summaries. Capsule persistence remains forbidden until a later admitted adapter exists.

Approval metadata is not execution because approval records include `approval_future_consideration_only` and explicitly forbid `execute_commit_plan_now`, `execute_operator_approval_now`, and `treat_approval_as_execution`.

Approval metadata is not policy, truth, consent, or authority. The packet blocks claims that approval proves truth, creates policy, grants consent, grants authority, converts approval to action, or bypasses upstream memory gates.

## Default-deny posture

The default policy requires:

- matching commit-plan packet digest;
- matching commit-plan decision;
- a commit-plan decision that is ready, warning-ready, deferred, rejected, or no-op;
- operator scope metadata;
- operator scope alignment with the plan scope;
- rollback expectation metadata for non-no-op approvals;
- receipt expectation metadata for non-no-op approvals.

Missing or mismatched evidence blocks by default. Mixed-scope diagnostic packets warn only when `allow_mixed_scope_diagnostic_packet` is explicitly true; otherwise mixed scope blocks with a scope-mismatch status. Operator review cannot override hard blockers such as raw payload leaks, execution claims, live write/delete claims, external disclosure, authority smuggling, consent/policy/truth claims, prompt materialization, action execution, index mutation, or capsule persistence.

## Candidate types

Supported approval candidate types are:

- `ai_capsule_commit_approval_candidate`
- `human_summary_commit_approval_candidate`
- `dual_capsule_commit_approval_candidate`
- `protect_receipt_commit_approval_candidate`
- `merge_receipt_commit_approval_candidate`
- `tomb_archive_commit_approval_candidate`
- `tomb_deferred_commit_approval_candidate`
- `operator_review_commit_approval_candidate`
- `noop_commit_approval_candidate`
- `mixed_commit_approval_candidate`

## Statuses and decisions

Successful statuses are `memory_commit_operator_approval_ready`, `memory_commit_operator_approval_ready_with_warnings`, `memory_commit_operator_approval_deferred_for_operator_review`, and `memory_commit_operator_approval_rejected`. Blocked statuses distinguish missing or invalid commit-plan packets, missing or invalid approval candidates, plan readiness failures, plan digest mismatch, plan decision mismatch, missing operator scope, scope mismatch, missing rollback or receipt expectations, approval overclaims, execution claims, live write/delete claims, index mutation claims, capsule persistence claims, prompt materialization, action execution, external disclosure, authority smuggling, and raw payload leaks.

Approval decisions are:

- `commit_approval_ready_for_future_adapter`
- `commit_approval_ready_for_future_adapter_with_warnings`
- `commit_approval_deferred_for_operator_review`
- `commit_approval_rejected`
- `commit_approval_blocked`
- `commit_approval_noop`

## Safe next actions and forbidden next steps

Safe next actions are limited to inspecting the approval packet, requiring operator review, preparing later schemas or gates, rerunning with corrected evidence, sustaining default deny, or deferring to the memory runtime/self-improvement boundaries.

Forbidden next steps include writing, deleting, or purging live memory; mutating raw fragments, distilled memory, or vector indexes; persisting capsules or summaries; applying protection or merge; completing tombs; executing commit plans or approval records; calling memory manager mutation helpers; assembling prompts; retrieving live context; executing action ingress; inferring truth, authority, consent, policy, or action from approval; bypassing upstream distillation/receipt/tomb/writer/boundary/plan/operator-review gates; and enabling external disclosure.

## CLI and artifacts

`scripts/build_memory_commit_operator_approval_packet.py` provides `build-default`, `evaluate`, `validate`, `summarize`, and `inspect-fixture`. Evaluation is deterministic JSON and writes only when an explicit output path is supplied. Fixture metadata under `tests/fixtures/memory_commit_operator_approval_packet/` is synthetic metadata only, with no images, audio, video, transcripts, encoded media, secrets, provider prompts, real private payloads, live memory paths, or real operator home paths.
