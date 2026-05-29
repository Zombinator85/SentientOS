# Selective Memory Distillation Receipt Gate

The selective memory distillation receipt gate is a deterministic, metadata-only
admission layer for future receipt actions over the
[selective memory distillation contract](selective_memory_distillation_contract.md).
It consumes explicit distillation packets and proposed receipt candidates, then
returns whether those candidates are admissible, warning-only, deferred for
operator review, rejected, no-op, or blocked.

The gate exists between distillation and any later receipt/writer layer. It is
not the writer, not the tomb verifier, not a prompt assembler, and not a source
of policy or authority. It never reads live memory directories by default, never
writes memory, never deletes memory, never mutates vector indexes, never invokes
providers or remote services, never discloses externally, and never executes
action ingress.

## Relationship to the distillation contract

The distillation contract evaluates supplied memory, observation, reflection,
context, affective, embodiment, and proof-governance metadata into retain,
distill, capsule, tomb-intent, protect, defer, merge, reject, or no-op decisions.
The receipt gate consumes the resulting packet and checks whether a future
receipt candidate matches the packet's record, decision, digest, tomb metadata,
and scope.

A receipt-gate decision does not create truth. It does not infer consent. It does
not grant authority. It does not convert memory evidence into policy. It only
states whether a later receipt/writer layer may be prepared under the same
non-authoritative metadata boundary.

## Non-authority boundaries

Every successful gate packet carries the invariant flags that the receipt gate is
not a memory write, not deletion, not tomb completion, not prompt assembly, not
policy, not authority, does not execute action, and does not disclose
externally. Successful packets also keep runtime memory mutation, prompt
materialization, external disclosure, and remote services disabled.

Tomb intent is not tomb completion. Tomb receipt candidates require tomb-intent
metadata and are blocked if they claim deletion has already occurred.

Capsule admissibility is not capsule persistence. Capsule receipt candidates can
be admissible only as future-intent metadata and are blocked if they include raw
private payloads, raw transcripts, media, encoded media, secrets, provider
prompts, or applied-state claims.

Protect and merge receipt candidates are future-intent only. They are blocked if
they claim protection or merge has already been applied.

Operator review cannot override hard blockers. Review and defer candidates can
route metadata to human attention, but they cannot transform unsafe payloads,
digest mismatches, tomb completion claims, prompt materialization, external
disclosure, action execution, authority smuggling, or runtime mutation into
admissible receipt actions.

## Receipt candidate types

- `ai_capsule_write_receipt_candidate`
- `human_summary_write_receipt_candidate`
- `dual_capsule_write_receipt_candidate`
- `tomb_intent_receipt_candidate`
- `tomb_after_distillation_receipt_candidate`
- `protect_memory_receipt_candidate`
- `merge_capsule_receipt_candidate`
- `operator_review_receipt_candidate`
- `defer_receipt_candidate`
- `reject_record_receipt_candidate`
- `no_op_receipt_candidate`

## Gate statuses

Ready statuses are `selective_memory_receipt_gate_ready` and
`selective_memory_receipt_gate_ready_with_warnings`. Blocked statuses cover
missing or invalid distillation packets, missing or invalid candidates, decision
mismatches, digest mismatches, missing tomb intent, claimed tomb completion,
unsafe capsule payloads, raw payload leaks, authority smuggling, prompt
materialization, runtime memory mutation, external disclosure, and scope
mismatch. Invalid and failed statuses are reserved for malformed or unexpected
gate failures.

## Gate decisions and safe next actions

Candidate decisions are:

- `receipt_candidate_admissible`
- `receipt_candidate_admissible_with_warnings`
- `receipt_candidate_deferred_for_operator_review`
- `receipt_candidate_blocked`
- `receipt_candidate_rejected`
- `receipt_candidate_noop`

Safe next actions are metadata-only signals such as
`inspect_receipt_gate_packet`, `operator_review_required`,
`prepare_capsule_writer_later`, `prepare_tomb_receipt_writer_later`,
`prepare_protect_receipt_later`, `prepare_merge_receipt_later`,
`rerun_with_matching_digest`, `rerun_with_tomb_intent`,
`rerun_with_safe_capsule`, `rerun_with_scope_alignment`,
`defer_to_memory_runtime_boundary`, and
`defer_to_self_improvement_ingress`.

## Forbidden next steps

Successful outputs explicitly forbid immediate memory writes, deletion, purge,
raw-fragment mutation, vector-index mutation, distilled-memory mutation, tomb
completion claims, capsule-written claims, protection-applied claims,
merge-applied claims, calls to memory-manager mutation functions, prompt
assembly, live-context retrieval, action ingress execution, truth/authority/
consent inference, policy conversion, action conversion, bypassing the
distillation contract, bypassing the memory tomb, bypassing operator review, and
enabling external disclosure.

## Source digest matching and scope alignment

By default, a candidate source digest must match the referenced distillation
record digest or the packet digest it claims. Candidate decision type must match
the distillation decision it claims to receipt. Scope mismatch blocks by default;
mixed-scope diagnostic packets can warn only when policy explicitly enables
mixed-scope diagnostics.

## Raw-to-distilled-to-capsule-to-tomb lifecycle

1. Raw source evidence remains outside this gate.
2. The selective memory distillation contract produces metadata-only decisions.
3. This receipt gate validates proposed future receipt actions over those
   decisions.
4. Later tomb or writer layers must still verify their own authority and safety.

The future sequence is:

1. Selective memory distillation contract.
2. Selective memory distillation receipt gate.
3. Tomb receipt verifier.
4. Governed memory writer adapter.
5. Self-improvement perception and affective ingress ledger.
6. GenesisForge embodied self-improvement handoff packet.
