# Selective Memory Tomb Receipt Verifier

The selective memory tomb receipt verifier is a deterministic, metadata-only layer that sits after the [selective memory distillation contract](selective_memory_distillation_contract.md) and the [selective memory distillation receipt gate](selective_memory_distillation_receipt_gate.md). It evaluates supplied distillation packets, receipt-gate packets, and tomb receipt claims to decide whether the claim is verified, verified with warnings, deferred, rejected, blocked, or a no-op.

The verifier exists to make tomb receipt metadata reviewable without granting runtime power. It only compares explicit JSON metadata: source digests, distillation decisions, receipt-gate decisions, tomb intent identifiers, tomb intent digests, source scopes, and non-authority safety flags. It never reads live memory directories by default and never treats a tomb receipt claim as proof that deletion happened.

## Relationship to the prior layers

1. **Selective memory distillation contract** decides whether supplied memory-related records should be retained, distilled, capsulized, protected, merged, deferred, rejected, tombed after distillation, tombed without retention, or treated as no distillation needed.
2. **Selective memory distillation receipt gate** evaluates whether a future receipt/write/tomb/protect/merge candidate is admissible, deferred, rejected, no-op, or blocked.
3. **Selective memory tomb receipt verifier** checks whether a tomb receipt claim is consistent with both prior evidence packets.

This verifier does not replace either prior layer. Digest matching and decision matching require prior contract and receipt-gate evidence, and successful verification never bypasses the distillation contract or receipt gate.

## Non-authority boundary

The verifier is not a memory writer, not deletion, and not tomb completion. It does not remove memory, write memory, write tomb receipts, persist capsules, apply protection, apply merges, mutate indexes, assemble prompts, disclose externally, call providers, execute actions, create policy, infer truth, infer consent, or grant authority.

Successful packets include explicit invariants such as:

- `tomb_verifier_is_not_memory_write: true`
- `tomb_verifier_is_not_deletion: true`
- `tomb_verifier_is_not_tomb_completion: true`
- `tomb_verifier_is_not_capsule_persistence: true`
- `tomb_verifier_is_not_prompt_assembly: true`
- `tomb_verifier_is_not_policy: true`
- `tomb_verifier_is_not_authority: true`
- `runtime_memory_mutation_enabled: false`
- `external_disclosure_enabled: false`
- `remote_service_enabled: false`

Observed deletion metadata is allowed only as untrusted external metadata when policy permits diagnostic warnings. By default, a claim of completed deletion blocks because the verifier cannot prove deletion and must not turn receipt metadata into deletion proof.

Capsule persistence, protection application, merge application, memory mutation, prompt materialization, external disclosure, raw/private/media payloads, authority smuggling, policy creation, truth inference, consent inference, and action execution claims block. Operator review can inspect or defer, but it cannot override hard blockers.

## Tomb claim types

- `tomb_intent_observed_receipt`
- `tomb_after_distillation_observed_receipt`
- `tomb_without_retention_observed_receipt`
- `tomb_deferred_for_writer_receipt`
- `tomb_blocked_receipt`
- `tomb_rejected_receipt`
- `tomb_noop_receipt`
- `tomb_mixed_receipt`

## Verifier statuses

Ready statuses are `selective_memory_tomb_receipt_verifier_ready` and `selective_memory_tomb_receipt_verifier_ready_with_warnings`. Blocked statuses distinguish missing or invalid distillation packets, missing or invalid receipt-gate packets, missing or invalid tomb claims, digest mismatch, decision mismatch, non-admissible receipt-gate evidence, missing or mismatched tomb intent, applied-state overclaim, memory mutation claims, unverified deletion claims, capsule persistence claims, raw payload leaks, authority smuggling, prompt materialization, external disclosure, and scope mismatch. Invalid and failed statuses are reserved for invalid or failed evaluation boundaries.

## Verification outcomes

- `tomb_receipt_verified`
- `tomb_receipt_verified_with_warnings`
- `tomb_receipt_deferred_for_operator_review`
- `tomb_receipt_rejected`
- `tomb_receipt_blocked`
- `tomb_receipt_noop`

Deferred, rejected, blocked, and no-op outcomes remain metadata observations; none are runtime effects.

## Safe and forbidden next steps

Safe next actions remain non-authoritative: inspect verification, operator review, prepare a governed memory writer later, prepare a tomb receipt archive later, rerun with matching digest, rerun with matching tomb intent, rerun with admissible receipt-gate evidence, rerun with scope alignment, sustain tomb deferral, defer to the memory runtime boundary, or defer to self-improvement ingress.

Every successful output forbids immediate deletion, purging, writing, raw mutation, vector-index mutation, distilled-memory mutation, claims that the verifier performed deletion or completed tombing, capsule/protect/merge persistence claims, memory manager calls, prompt assembly, live-context retrieval, action ingress execution, truth/authority/consent inference, policy conversion, action conversion, bypassing prior gates, and external disclosure.

## Matching rules

Source digest matching checks the tomb claim against the referenced distillation record digest, record source digest, distillation packet digest, or receipt-gate decision digest. Tomb intent matching requires a tomb intent identifier and digest when tomb-intent receipts are verified. Scope alignment compares claim, distillation record, and receipt-gate scopes; mixed-scope diagnostics warn only when explicitly allowed by policy.

## Raw to distilled to capsule to tomb lifecycle

The lifecycle remains staged and governed: raw memory metadata is evaluated by the distillation contract, future write/tomb/protect/merge paths are checked by the receipt gate, tomb receipt claims are verified by this verifier, and any actual persistence or deletion must be handled later by a governed runtime boundary.

Future sequence:

1. selective memory distillation contract
2. selective memory distillation receipt gate
3. selective memory tomb receipt verifier
4. governed memory writer adapter
5. self-improvement perception and affective ingress ledger
6. GenesisForge embodied self-improvement handoff packet
