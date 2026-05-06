# Phase 78 Operator Review Receipt Contract Execplan

## Goal

Phase 78 adds a deterministic, metadata-only operator review receipt that can be attached to a Phase 77 prompt materialization policy decision when operator review is required. The artifact records reviewer identity metadata, accepted/rejected warning and caveat codes, expiration metadata, findings, and digest linkage without granting runtime authority.

## Non-goals

- Do not materialize prompt text.
- Do not assemble final prompts.
- Do not call an LLM or provider SDK.
- Do not retrieve or write memory.
- Do not trigger feedback, commit retention, route/admit/execute work, or touch action surfaces.
- Do not modify live `assemble_prompt(...)` behavior.
- Do not add a UI.
- Do not override hard policy denials.

## Phase 61 through Phase 77 dependency chain

Phase 78 sits after the existing context-hygiene runway:

1. Phase 61: `ContextPacket` schema and context assembly receipts.
2. Phase 62: truth-gated context selection.
3. Phase 62B: blocked risk and attempted-candidate contamination preservation.
4. Phase 63: embodiment/privacy context eligibility adapters.
5. Phase 64: prompt preflight.
6. Phase 65: packet-local safety metadata preservation.
7. Phase 66: source-kind safety contracts.
8. Phase 67: prompt handoff manifest.
9. Phase 68: prompt assembly dry-run envelope.
10. Phase 69: prompt assembly constraint verifier.
11. Phase 70: prompt assembly adapter contract.
12. Phase 71: prompt assembler compliance harness.
13. Phase 72: shadow adapter preview hook.
14. Phase 73: shadow blueprint contract.
15. Phase 74: prompt materialization audit receipt / attestation.
16. Phase 75: static prompt-boundary guardrails.
17. Phase 76: adversarial/property-style failure-mode tests.
18. Phase 77: pure policy decision layer.
19. Phase 78: operator review receipt contract for review-required warnings/caveats only.

## Operator review is not materialization

The receipt is an attestation-like metadata artifact. It stores IDs, policy status, digest links, rings, packet scope, review scope, decisions, warning/caveat codes, expiration metadata, findings, and boolean non-runtime markers. It does not contain prompt bodies, assembled prompt text, raw payloads, memory contents, tool handles, model parameters, or runtime authority.

## Operator review is not a hard-block override

Operator review may satisfy policy-required warnings/caveats only. It cannot override:

- blocked refs or blocked audit receipts,
- invalid digest chains,
- runtime wiring,
- prompt text markers,
- raw payload markers,
- runtime authority markers,
- missing provenance or digest mismatch,
- action/retention/memory/tool capabilities,
- unknown source kinds,
- `policy_deny`, `policy_invalid_input`, or `policy_runtime_wiring_detected`,
- live/internal/LLM-capable rings.

## Receipt shape

`PromptOperatorReviewReceipt` includes:

- `review_receipt_id`, `review_status`, and `review_digest`,
- Phase 77 linkage: `policy_decision_id`, `policy_status`, `policy_digest`, `requested_ring`, `effective_ring`,
- audit linkage: `receipt_id` and `audit_receipt_digest`,
- packet linkage: `packet_id` and `packet_scope`,
- `reviewer_ref`, `review_scope`, and `decisions`,
- accepted/rejected warning and caveat codes,
- required warning and caveat codes derived from Phase 77 review-required reasons/mitigations and counts,
- `expiration`, `expired`, `forbidden_override_attempted`, `findings`, and compact rationale,
- explicit non-runtime markers asserting no prompt materialization, no LLM call, no memory IO, no feedback, no retention, no execution/routing/admission.

## Warning/caveat acceptance behavior

Phase 78 derives stable review-required codes from the Phase 77 decision metadata. If warnings or caveats require review, the receipt must record accepted codes for all required warning/caveat codes to satisfy the policy decision. Rejected codes remain visible and cause rejection. Partial acceptance is represented as `review_partially_accepted`, but the satisfaction helper still requires all required warning/caveat codes to be accepted.

## Forbidden override rules

A receipt is marked `review_forbidden_override_attempted` when acceptance decisions or accepted codes are attached to hard-denied policy decisions, runtime-wiring decisions, invalid input decisions, hard denial reasons, or live/internal/LLM-capable rings. Such receipts never satisfy policy.

## Digest behavior

`compute_prompt_operator_review_digest(...)` hashes stable metadata-safe fields only. The digest changes when policy digest, reviewer reference, decisions, accepted/rejected codes, expiration, status, findings, or rationale change. It excludes prompt text, raw payloads, runtime handles, LLM parameters, and nondeterministic timestamps unless those timestamps are explicitly provided as stable input.

## Policy relationship

Phase 78 does not mutate Phase 77 decisions and does not alter live runtime behavior. `operator_review_satisfies_policy_decision(...)` returns true only for a matching, unexpired, accepted review receipt attached to a policy decision that requires operator review and has no forbidden override attempt.

## Tests

The Phase 78 test suite covers accepted, rejected, partial, expired, mismatched, forbidden override, digest, non-runtime marker, guardrail, import-purity, and full runway integration behavior.

## Deferred work

- UI presentation of receipt summaries.
- Durable operator review storage.
- Human workflow integrations.
- Future synthetic-only materializer wiring after a separate boundary review.
