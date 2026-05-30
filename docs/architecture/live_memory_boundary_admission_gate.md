# Live Memory Boundary Admission Gate

The live memory boundary admission gate is a deterministic, metadata-only review gate between governed writer artifacts and any future live-memory boundary. It exists so reviewers can ask whether an explicit governed writer artifact is eligible for a later live-memory boundary review without granting that artifact authority, applying it to memory, or treating it as truth.

## Position in the memory chain

The gate is downstream of four existing review-only layers:

1. The [selective memory distillation contract](selective_memory_distillation_contract.md) records metadata-only distillation, capsule, summary, and tomb-intent decisions.
2. The [selective memory distillation receipt gate](selective_memory_distillation_receipt_gate.md) validates receipt candidates over distillation decisions without writing memory.
3. The [selective memory tomb receipt verifier](selective_memory_tomb_receipt_verifier.md) validates tomb-related evidence without proving deletion or completing tombs.
4. The [governed memory writer adapter](governed_memory_writer_adapter.md) creates dry-run previews or explicit local JSON artifact receipts while still blocking live memory paths by default.
5. The live memory boundary admission gate evaluates those packets for future boundary-review eligibility only.

Admission is not memory writing, not deletion, not capsule persistence, not policy, not truth, not consent, not authority, and not action execution. It does not assemble prompts, retrieve live context, invoke providers, disclose externally, mutate indexes, or write to live-memory stores.

## Default-deny and future review

The default boundary posture is `deny`. A successful admission packet only says that the supplied metadata is eligible for a later boundary review. Future review remains required before any memory commit plan, live memory commit adapter, self-improvement ingress ledger, or GenesisForge handoff can act. Operator review can defer or inspect the packet, but it cannot override hard blockers such as digest mismatches, live write claims, deletion claims, prompt materialization, action execution, external disclosure, raw payload leaks, authority smuggling, or scope mismatch.

## Candidate types

Supported admission candidate types are:

- `ai_capsule_boundary_candidate`
- `human_summary_boundary_candidate`
- `dual_capsule_boundary_candidate`
- `protect_receipt_boundary_candidate`
- `merge_receipt_boundary_candidate`
- `tomb_receipt_boundary_candidate`
- `tomb_deferred_boundary_candidate`
- `operator_review_boundary_candidate`
- `noop_boundary_candidate`
- `mixed_boundary_candidate`

Tomb-related candidates require tomb verifier metadata when policy requires it. Mixed-scope diagnostic packets warn only when policy explicitly enables mixed-scope diagnostics; otherwise scope mismatch blocks.

## Admission statuses and decisions

The gate can return ready, ready-with-warnings, deferred-for-operator-review, or blocked statuses. Blocked statuses distinguish missing or invalid upstream packets, missing or invalid candidates, digest mismatch, decision mismatch, not-ready writer decisions, unverified tomb evidence, live write/delete/index/capsule/prompt/action/external-disclosure claims, authority smuggling, raw payload leaks, and scope mismatch.

Admission decisions are:

- `boundary_review_candidate_ready`
- `boundary_review_candidate_ready_with_warnings`
- `boundary_review_deferred_for_operator_review`
- `boundary_review_blocked`
- `boundary_review_rejected`
- `boundary_review_noop`

## Digest matching and scope alignment

Each candidate must claim the same source digest as the referenced distillation, receipt-gate, tomb-verifier when applicable, and governed-writer evidence. It must also claim upstream decisions matching those records. Scope keys must align by default so evidence from one scope cannot be smuggled into another. The output packet and report include deterministic SHA-256 digests over canonical JSON.

## Safe next actions

Successful packets can include safe actions such as `inspect_boundary_admission_packet`, `operator_review_required`, `prepare_live_memory_review_packet_later`, `prepare_memory_commit_plan_later`, `prepare_tomb_review_packet_later`, `prepare_capsule_review_packet_later`, `sustain_default_deny`, `defer_to_memory_runtime_boundary`, and `defer_to_self_improvement_ingress`. These are labels for later review, not effects.

## Forbidden next steps and invariants

Every successful packet repeats forbidden next steps including `write_live_memory_now`, `delete_live_memory_now`, `purge_live_memory_now`, `mutate_vector_index`, `persist_capsule_now`, `apply_protection_now`, `apply_merge_now`, `complete_tomb_now`, `assemble_prompt_now`, `retrieve_live_context`, `execute_action_ingress`, `infer_truth_from_admission`, `infer_authority_from_admission`, `infer_consent_from_admission`, `convert_admission_to_policy`, `convert_admission_to_action`, `bypass_governed_writer_adapter`, and `enable_external_disclosure`.

Every successful packet also asserts non-authority invariants: admission is not memory write, not memory deletion, not index mutation, not capsule persistence, not prompt assembly, not truth, not policy, not authority, not consent, does not execute actions, does not disclose externally, does not enable live writes/deletions/index mutation/capsule persistence/prompt materialization/external disclosure/remote services, remains default-deny, and requires future review.

## Raw-to-boundary lifecycle

The intended raw-to-distilled-to-capsule-to-receipt-to-writer-to-boundary lifecycle is:

1. Selective memory distillation contract.
2. Selective memory distillation receipt gate.
3. Selective memory tomb receipt verifier.
4. Governed memory writer adapter.
5. Live memory boundary admission gate.
6. Memory commit plan packet.
7. Live memory commit adapter only after explicit later admission.
8. Self-improvement perception and affective ingress ledger.
9. GenesisForge embodied self-improvement handoff packet.

This document describes step 5 only. It deliberately preserves the future boundary as a separate, explicit, auditable review.
