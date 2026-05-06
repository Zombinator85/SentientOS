# Phase 74: Prompt Materialization Audit Receipt / Attestation Exec Plan

## Goal
Add a deterministic, append-safe Prompt Materialization Audit Receipt / Attestation contract that binds the shadow prompt assembly runway into one verifiable artifact before any prompt text materialization exists.

The receipt attests to upstream identities, digests, statuses, caveats, warnings, violations, boundary markers, provenance/privacy/truth/safety summaries, source-kind/ref/section counts, and a deterministic receipt digest.

## Non-goals
- No prompt text materialization.
- No final prompt assembly.
- No LLM calls.
- No memory retrieval or memory writes.
- No feedback, retention, action, routing, admission, execution, orchestration, truth, or embodiment runtime behavior changes.
- No live `assemble_prompt(...)` behavior changes.
- No source rehydration, raw candidate access, raw memory, raw screen/audio/vision/multimodal payloads, runtime handles, or LLM parameter transport.

## Dependency chain
Phase 74 depends on the context hygiene spine:

1. **Phase 61**: `ContextPacket` schema and receipts.
2. **Phase 62**: truth-gated context selection.
3. **Phase 62B**: first-class `blocked` risk and attempted-candidate contamination preservation.
4. **Phase 63**: embodiment/privacy context eligibility adapters.
5. **Phase 64**: prompt preflight.
6. **Phase 65**: packet-local safety metadata preservation.
7. **Phase 66**: source-kind safety contracts.
8. **Phase 67**: context prompt handoff manifest.
9. **Phase 68**: prompt assembly dry-run envelope.
10. **Phase 69**: prompt assembly constraint verifier.
11. **Phase 70**: prompt assembly adapter contract.
12. **Phase 71**: prompt assembler compliance harness.
13. **Phase 72**: prompt assembler shadow adapter preview hook.
14. **Phase 73**: prompt assembler shadow blueprint contract.

## Audit receipt is not prompt materialization
The Phase 74 receipt is an attestation artifact only. It records IDs, digests, statuses, caveats, warnings, violations, boundary summaries, provenance/privacy/truth/safety summaries, source-kind/ref/section counts, deterministic findings, and a receipt digest. It deliberately omits final prompt text, prompt fragments, raw payloads, hidden chain-of-thought, runtime handles, LLM parameters, and nondeterministic timestamps.

## Receipt output shape
`PromptMaterializationAuditReceipt` includes:

- `receipt_id`
- `audit_status`
- `blueprint_id` / `blueprint_digest`
- `adapter_payload_id` / `adapter_status` / `adapter_payload_digest`
- `compliance_status`, `preview_status`, and `blueprint_status`
- packet, manifest, envelope, candidate-plan, verification, preview, and blueprint chain fields where exposed by upstream contracts
- `digest_chain_complete` and structured `digest_chain`
- `boundary_summary`
- `preserved_caveats`
- `warnings`, `violations`, and `findings`
- provenance/privacy/truth/safety summaries
- source-kind summary, ref counts, and section counts
- compact rationale
- deterministic `receipt_digest`
- explicit no-runtime markers including audit-only, attestation-only, no prompt text materialization, no prompt assembly, no LLM calls, no memory retrieval/writes, no feedback/retention, and no execution/routing/admission.

## Digest chain behavior
The receipt binds every currently exposed upstream digest into a stable digest chain. Required current-contract fields include the shadow blueprint digest, adapter payload digest, envelope digest, packet id, packet scope, adapter payload id, and blueprint id. Manifest digest is included when carried by assembly constraints. Verification, candidate-plan, and shadow-preview digests are left empty when upstream phases do not expose them; Phase 74 does not invent upstream digests.

The receipt digest is deterministic over receipt-safe stable fields and changes when audit status, blueprint digest, adapter payload digest, envelope digest, warnings, violations, caveats, boundary summary, or counts change. It excludes raw payloads, final prompt text, hidden chain-of-thought, runtime handles, LLM parameters, and nondeterministic timestamps.

## Gating behavior
`audit_receipt_allows_shadow_materializer(...)` returns true only when:

- audit status is `audit_ready_for_shadow_materialization` or `audit_ready_with_warnings`;
- the current-contract digest chain is complete;
- no raw payloads are present;
- no final prompt text is present;
- no runtime authority is present;
- required non-runtime markers are present;
- the Phase 73 blueprint may be consumed by a future assembler;
- the Phase 73 blueprint does not block prompt materialization.

Blocked, not-applicable, invalid, invalid-chain, and runtime-wiring-detected receipts never allow shadow materialization.

## Status mapping
- `shadow_blueprint_ready` → `audit_ready_for_shadow_materialization`
- `shadow_blueprint_ready_with_warnings` → `audit_ready_with_warnings`
- `shadow_blueprint_blocked` → `audit_blocked`
- `shadow_blueprint_not_applicable` → `audit_not_applicable`
- `shadow_blueprint_invalid_adapter_payload` → `audit_invalid_blueprint`
- `shadow_blueprint_runtime_wiring_detected` → `audit_runtime_wiring_detected`
- missing or inconsistent required current-contract chain evidence → `audit_invalid_chain`

## Findings taxonomy
Phase 74 uses compact deterministic finding codes including:

- `missing_blueprint_id`
- `missing_blueprint_digest`
- `missing_adapter_payload_id`
- `missing_packet_id`
- `missing_packet_scope`
- `missing_envelope_digest`
- `missing_adapter_payload_digest`
- `missing_required_non_runtime_marker`
- `digest_chain_incomplete`
- `digest_chain_mismatch`
- `blocked_blueprint`
- `invalid_blueprint`
- `not_applicable_blueprint`
- `runtime_wiring_detected`
- `prompt_text_present`
- `raw_payload_present`
- `runtime_authority_present`
- `materialization_not_allowed`
- `caveat_requires_review`
- `warning_requires_review`

## Relationship to a future shadow text materializer
Phase 74 is a prerequisite gate for any future shadow text materializer. A future phase may define a synthetic or shadow text materialization harness, but it must first consume and verify a Phase 74 audit receipt and must preserve the no-runtime/no-authority boundaries unless a later phase explicitly changes those boundaries with new tests and review.

## Tests
`tests/test_phase74_prompt_materialization_audit_receipt.py` covers ready, warning, blocked, not-applicable, invalid, runtime-wiring, identity/digest/status fields, packet scope, caveats, warnings, violations, boundary summaries, digest-chain determinism, invalid-chain findings, digest sensitivity, no-prompt/no-raw/no-runtime helpers, materializer gating, mutation safety, runtime isolation, Phase 63-to-74 flow, Phase 62B blocked flow, and import/export expectations.

## Deferred work
- Real prompt text materialization remains deferred.
- Synthetic shadow text materializer remains deferred.
- Runtime integration, LLM/provider calls, memory retrieval/writes, feedback, retention, action, routing, admission, execution, and orchestration remain deferred.
- Upstream candidate-plan, verification, and shadow-preview digest exposure may be added in future phases if needed.
