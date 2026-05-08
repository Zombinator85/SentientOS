# Phase 81: Internal Candidate Display Receipt / Egress Boundary Exec Plan

## Goal

Phase 81 adds a deterministic, metadata-only display receipt for Phase 80 `InternalPromptCandidate` objects. The receipt decides whether already-rendered internal candidate text may be shown or exported to an operator-only internal review/debug/audit surface.

The receipt is an egress-control contract only. It is not UI, not model invocation, not prompt assembly, and not runtime authority.

## Non-goals

- Do not call an LLM or send candidate text to a model/provider.
- Do not retrieve memory, write memory, trigger feedback, or commit retention.
- Do not execute tools/actions, route work, admit work, fulfill work, or orchestrate runtime behavior.
- Do not modify `prompt_assembler.py` or live `assemble_prompt(...)` behavior.
- Do not add UI or a general runtime prompt assembly/export path.
- Do not duplicate full Phase 80 candidate text into the display receipt.

## Dependency chain

Phase 81 depends on the Phase 61 through Phase 80 context-hygiene spine:

1. Phase 61 context packet schema and receipts.
2. Phase 62 truth-gated context selection.
3. Phase 62B first-class blocked risk and attempted-candidate contamination preservation.
4. Phase 63 embodiment/privacy eligibility adapters.
5. Phase 64 prompt preflight.
6. Phase 65 packet-local safety metadata preservation.
7. Phase 66 source-kind safety contracts.
8. Phase 67 prompt handoff manifest.
9. Phase 68 prompt assembly dry-run envelope.
10. Phase 69 prompt assembly constraint verifier.
11. Phase 70 prompt assembly adapter contract.
12. Phase 71 prompt assembler compliance harness.
13. Phase 72 shadow adapter preview hook.
14. Phase 73 shadow blueprint contract.
15. Phase 74 prompt materialization audit receipt.
16. Phase 75 static prompt-boundary guardrails.
17. Phase 76 adversarial/property failure-mode tests.
18. Phase 77 pure policy decision layer.
19. Phase 78 operator review receipt contract.
20. Phase 79 synthetic-only prompt candidate harness.
21. Phase 80 internal/operator-visible no-LLM prompt candidate contract.

## Display receipt is not UI

`prompt_internal_display.py` creates receipts and validation helpers only. It renders no interface, opens no file/browser surface, and exports no object that contains duplicated candidate text.

## Display receipt is not model egress

The display receipt carries explicit markers that model/provider egress remains forbidden:

- `no_llm=True`
- `model_egress=False`
- `live_model_call=False`
- `does_not_call_llm=True`

The receipt helper imports no provider SDKs and never calls provider/model APIs.

## Display scopes

Allowed Phase 81 display scopes are metadata-only:

- `operator_internal_review`
- `operator_internal_debug`
- `audit_replay`

Forbidden scopes are:

- `external_user_visible_forbidden`
- `model_provider_forbidden`
- `tool_or_action_forbidden`
- any unknown scope

## Receipt shape

`InternalPromptDisplayReceipt` links display egress to candidate, policy, audit, review, and packet evidence. It records the display scope, operator reference, reason, candidate digest, expected candidate digest, digest match state, candidate text digest/length, expiration state, findings, warnings, rationale, and a deterministic `display_receipt_digest`.

The receipt also repeats no-runtime boundary markers for LLM, memory, feedback, retention, tool/action, routing, admission, prompt assembly, and model-call prohibitions.

## Text digest/length behavior

The receipt records only:

- `candidate_text_digest`
- `candidate_text_length`
- `text_included=False`
- `text_redacted=True`

Full `internal_candidate_text` remains on the original Phase 80 candidate. A future display surface must validate the receipt and then read text from the original candidate; Phase 81 itself does not duplicate or export that text.

## Gating rules

Display is allowed only when all gates pass:

- Candidate status is `internal_prompt_candidate_ready` or `internal_prompt_candidate_ready_with_warnings`.
- Candidate is internal-only, operator-visible-only, and no-LLM.
- Candidate has no live prompt assembly, live model call, runtime authority, or tool/action capability.
- Candidate digest is stable and matches any expected digest.
- Policy, audit, review, and packet linkage is present on the candidate.
- Display scope is operator-internal or audit replay.
- `operator_ref` is present.
- Receipt is not expired.
- Candidate text contains the Phase 80 internal no-LLM, not-sent-to-model, and operator-visible-only markers.
- Candidate text contains no raw-payload, runtime-handle, or provider-parameter markers.

Blocked, invalid, policy-denied, review-required, digest-mismatched, forbidden-scope, model-egress, external-user-egress, tool/action-egress, or runtime-authority cases deny display.

## Guardrail behavior

Phase 81 extends the Phase 75 static guardrail scan target list to include `sentientos/context_hygiene/prompt_internal_display.py`. It does not expand the prompt-text allowlist. The only prompt text field allowlists remain Phase 79 `synthetic_prompt_text` and Phase 80 `internal_candidate_text` in their scoped modules/tests.

The new module must not import `prompt_assembler.py`, memory/runtime modules, provider SDKs, action/retention/routing modules, or call `assemble_prompt(...)`.

## Tests

`tests/test_phase81_internal_candidate_display_receipt.py` covers allowed ready and ready-with-warning candidates; blocked, invalid, policy-denied, review-required, digest mismatch, forbidden scope, missing operator, expired receipt, adversarial text markers, deterministic text/receipt digests, evidence linkage, no-runtime markers, no model egress, no mutation, no runtime imports/calls, Phase 63-to-81 smoke behavior, Phase 62B blocked attempted-candidate denial, Phase 76 adversarial marker denial, and Phase 75 guardrail coverage.

## Deferred work

Future work may add an actual internal review UI or a later internal model-call review gate. Those phases must validate this receipt before display/export and must introduce separate authorization for any new egress or runtime behavior. Phase 81 grants none of that authority.
