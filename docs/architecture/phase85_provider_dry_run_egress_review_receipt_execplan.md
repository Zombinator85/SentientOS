# Phase 85 Provider Dry-Run Egress Review Receipt Execplan

## Goal

Phase 85 adds a deterministic, metadata-only `ProviderDryRunEgressReviewReceipt` for Phase 84 `ProviderDryRunRequestEnvelope` objects. The receipt records whether an operator or reviewer approves, denies, expires, or constrains a non-sendable provider dry-run envelope for a future provider-call simulation gate or future egress-review gate.

## Non-goals

- Do not invoke an LLM, provider SDK, provider client, endpoint, credential, or transport.
- Do not send prompt text to any model/provider.
- Do not make network calls.
- Do not retrieve memory, write memory, trigger feedback, commit retention, execute tools/actions, route work, admit work, fulfill work, or orchestrate work.
- Do not modify `prompt_assembler.py` or live `assemble_prompt(...)` behavior.
- Do not create a runtime model-call path or a sendable provider request.

## Dependency chain: Phase 61 through Phase 84

Phase 85 sits after the existing context-hygiene spine:

1. Phase 61: `ContextPacket` schema and receipts.
2. Phase 62/62B: truth-gated selection and blocked-risk contamination preservation.
3. Phase 63: embodiment/privacy eligibility adapters.
4. Phase 64 through Phase 67: prompt preflight and handoff metadata.
5. Phase 68 through Phase 73: dry-run, constraint verification, adapter/compliance/shadow blueprint contracts.
6. Phase 74 through Phase 78: audit, guardrails, adversarial tests, policy decisions, and operator review receipts.
7. Phase 79 through Phase 81: synthetic-only candidate, internal no-LLM candidate, and internal display receipt boundary.
8. Phase 82 and Phase 83: internal model-call preflight and model-call review receipt that still forbid provider invocation.
9. Phase 84: non-sendable provider dry-run request envelope.
10. Phase 85: provider dry-run egress review receipt over the Phase 84 envelope.

## Egress review receipt is not provider invocation

The receipt is review metadata only. It may approve only:

- `future_provider_simulation_gate`
- `future_egress_review_gate`

It never approves actual provider send, network egress, credential use, provider SDK/client use, endpoint use, tool calls, memory authority, retention authority, action authority, routing/admission/execution authority, or external-user-visible egress.

## Review statuses and scopes

Statuses are deterministic compact strings:

- `provider_dry_run_review_approved`
- `provider_dry_run_review_approved_with_constraints`
- `provider_dry_run_review_rejected`
- `provider_dry_run_review_expired`
- `provider_dry_run_review_invalid`
- `provider_dry_run_review_forbidden_send_override_attempted`
- `provider_dry_run_review_not_applicable`

Scopes are metadata-only:

- `future_provider_simulation_gate`
- `future_egress_review_gate`
- `actual_provider_send_forbidden`
- `network_egress_forbidden`
- `credential_use_forbidden`
- `tool_or_action_forbidden`
- `external_user_visible_forbidden`

Only the two future-gate scopes can approve. Forbidden scopes are non-overridable.

## Required mitigation behavior

Required mitigation codes are derived deterministically from Phase 84 findings, warnings, constraints, ready-with-warnings status, and provider/network/credential/client forbidden markers. A review satisfies an envelope only when every required mitigation or constraint is accepted or approved and no required mitigation/constraint is rejected.

## Forbidden send override rules

An approving review is marked as a forbidden override attempt when it tries to approve blocked, invalid, send-forbidden, credential-detected, network-egress-detected, runtime-authority-detected, or unknown provider/model-label envelopes. It is also non-overridable if any provider/network/credential/client/LLM/tool/memory/retention/action/routing allowance is true, evidence linkage is missing, or the review targets forbidden scopes.

## Non-sendable/provider-forbidden constraints

Receipts preserve explicit false allowances for provider send, network egress, credentials, provider clients, LLM calls, tools, memory retrieval/writes, retention, action execution, and routing. They also preserve true markers for provider-send-forbidden, network-egress-forbidden, credentials-forbidden, provider-client-forbidden, LLM-call-forbidden, non-sendable preservation, no network calls, no provider sends, no memory retrieval/writes, no retention, no runtime execution/routing, and no work admission.

## Digest behavior

The review digest is SHA-256 over stable metadata-safe fields only. It changes when dry-run digest, reviewer ref, decision, scope, approved/rejected constraints, accepted/rejected mitigations, expiration, status, findings, or rationale changes. It excludes prompt text, raw payloads, credentials, endpoints, provider handles, runtime handles, provider parameters, and nondeterministic timestamps unless explicitly supplied as stable metadata.

## Guardrail behavior

`prompt_provider_dry_run_review.py` is included in the default context-hygiene prompt-boundary scan. The scan must reject provider SDK imports, network clients, `prompt_assembler.py`, memory manager imports, runtime/action/retention/routing modules, live `assemble_prompt(...)` calls, provider/model API calls, network APIs, memory APIs, action/retention/routing APIs, and tool/runtime code.

## Tests

Phase 85 tests cover ready and warning envelopes, approval/constrained/rejection/expiration/invalid statuses, id/digest mismatch, forbidden dry-run statuses, forbidden scopes, forbidden allowance bits, missing evidence linkage, required mitigation satisfaction, non-sendable markers, digest determinism and change triggers, no mutation, no runtime/provider calls, Phase 63-to-84-to-85 continuity, blocked attempted-candidate behavior, adversarial marker non-overridability, guardrail scan coverage, and architecture/import purity compatibility.

## Deferred work

Future phases may add a provider-call simulation contract or an additional egress gate, but those future phases must consume this receipt as metadata only and must add their own guardrails before any simulation. Phase 85 itself remains non-sendable and grants no authority to call a provider.
