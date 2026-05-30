# Memory Commit Plan Packet

The memory commit plan packet is the sixth metadata-only layer in the selective
memory chain. It exists so reviewers can inspect what a later live-memory commit
adapter may be allowed to consider without allowing this layer to perform the
commit itself.

## Relationship to upstream evidence

The packet requires explicit JSON metadata from these upstream layers:

1. [Selective memory distillation contract](selective_memory_distillation_contract.md), which records distilled capsule, summary, retain, merge, protect, tomb, review, or no-op metadata without writing memory.
2. [Selective memory distillation receipt gate](selective_memory_distillation_receipt_gate.md), which checks receipt admissibility without writing receipts into live memory.
3. [Selective memory tomb receipt verifier](selective_memory_tomb_receipt_verifier.md), when tomb archive or tomb deferral candidates are supplied.
4. [Governed memory writer adapter](governed_memory_writer_adapter.md), which may produce governed artifact previews or receipts while still blocking live memory and live indexes.
5. [Live memory boundary admission gate](live_memory_boundary_admission_gate.md), which decides whether governed writer metadata is eligible for future boundary review.

A memory commit plan packet evaluates matching record identifiers, source
digests, upstream decisions, scope keys, rollback expectations, receipt
expectations, and proposed future operation metadata. Digest mismatch, decision
mismatch, missing upstream evidence, or scope mismatch blocks by default.

## What commit planning is not

Commit planning is not memory writing, deletion, capsule persistence, vector
index mutation, prompt assembly, action execution, external disclosure, truth,
policy, consent, or authority. It does not call memory manager APIs, does not
assemble live context, does not persist capsules or summaries, does not apply
protection or merge decisions, and does not complete tombs.

The default commit posture is deny. A successful packet only says that a future
commit adapter may be prepared later under separate explicit admission. The
packet includes `future_commit_adapter_required: true`,
`rollback_expectation_required: true`, and `receipt_expectation_required: true`
so every non-noop plan remains reviewable and reversible before any later live
commit mechanism exists.

Operator review can defer or inspect a plan, but it cannot override hard
blockers such as raw payload leaks, authority smuggling, digest mismatch, scope
mismatch, live-write claims, live-delete claims, prompt materialization, action
execution, or external disclosure.

## Plan candidate types

Supported candidate types are:

- `ai_capsule_commit_plan_candidate`
- `human_summary_commit_plan_candidate`
- `dual_capsule_commit_plan_candidate`
- `protect_receipt_commit_plan_candidate`
- `merge_receipt_commit_plan_candidate`
- `tomb_archive_commit_plan_candidate`
- `tomb_deferred_commit_plan_candidate`
- `operator_review_commit_plan_candidate`
- `noop_commit_plan_candidate`
- `mixed_commit_plan_candidate`

## Plan operation types

All operations are future proposals only:

- `propose_capsule_commit`
- `propose_summary_commit`
- `propose_dual_capsule_commit`
- `propose_protect_receipt_commit`
- `propose_merge_receipt_commit`
- `propose_tomb_archive_commit`
- `propose_tomb_deferral_commit`
- `propose_operator_review_archive`
- `propose_noop`
- `propose_mixed_commit_plan`

Any operation claiming applied, performed, completed, or executed state blocks.

## Plan statuses and decisions

Successful or deferred statuses include `memory_commit_plan_ready`,
`memory_commit_plan_ready_with_warnings`, and
`memory_commit_plan_deferred_for_operator_review`. Blocked statuses distinguish
missing or invalid distillation packets, receipt-gate packets, tomb-verifier
packets, writer packets, boundary-admission packets, and plan candidates;
digest mismatch; decision mismatch; boundary not ready; writer not ready; tomb
not verified; live-write claims; live-delete claims; index-mutation claims;
capsule-persistence claims; prompt materialization; action execution; external
disclosure; authority smuggling; raw payload leaks; and scope mismatch.

Plan decisions are `commit_plan_ready_for_review`,
`commit_plan_ready_for_review_with_warnings`,
`commit_plan_deferred_for_operator_review`, `commit_plan_blocked`,
`commit_plan_rejected`, and `commit_plan_noop`.

## Safe and forbidden next steps

Safe next actions include inspecting the packet, requiring operator review,
preparing later commit/rollback/receipt schemas, preparing later tomb or capsule
adapters, rerunning with matching digest/ready evidence/scope alignment, and
sustaining default-deny. Safe next actions do not execute the plan.

Every successful packet repeats forbidden next steps including
`write_live_memory_now`, `delete_live_memory_now`, `purge_live_memory_now`,
`mutate_vector_index`, `persist_capsule_now`, `persist_summary_now`,
`apply_protection_now`, `apply_merge_now`, `complete_tomb_now`,
`execute_commit_plan_now`, `assemble_prompt_now`, `retrieve_live_context`,
`execute_action_ingress`, `infer_truth_from_commit_plan`,
`infer_authority_from_commit_plan`, `convert_commit_plan_to_policy`,
`convert_commit_plan_to_action`, `bypass_live_boundary_admission`, and
`enable_external_disclosure`.

## Lifecycle sequence

The intended future sequence remains:

1. selective memory distillation contract
2. selective memory distillation receipt gate
3. selective memory tomb receipt verifier
4. governed memory writer adapter
5. live memory boundary admission gate
6. memory commit plan packet
7. live memory commit adapter only after explicit later admission
8. self-improvement perception and affective ingress ledger
9. GenesisForge embodied self-improvement handoff packet
