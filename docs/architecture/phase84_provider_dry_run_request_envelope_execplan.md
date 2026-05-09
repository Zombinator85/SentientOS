# Phase 84 Provider Dry-Run Request Envelope Execplan

## Goal

Phase 84 adds a deterministic provider-shaped dry-run request envelope that binds the Phase 80 `InternalPromptCandidate`, Phase 81 `InternalPromptDisplayReceipt`, Phase 82 `InternalModelCallPreflight`, and Phase 83 `InternalModelCallReviewReceipt` into one auditable artifact. The artifact can show what a future provider-shaped request might resemble while remaining explicitly non-sendable.

## Non-goals

- No LLM call.
- No provider/model send.
- No provider SDK import or provider client construction.
- No network egress.
- No memory retrieval or memory write.
- No feedback trigger or retention commit.
- No tool/action execution.
- No routing, admission, fulfillment, execution, or orchestration.
- No live `assemble_prompt(...)` behavior change.
- No `prompt_assembler.py` modification.
- No runtime model-call path.

## Phase 61 through Phase 83 Dependency Chain

Phase 84 depends on the existing context-hygiene spine:

1. Phase 61 packet schemas and receipts.
2. Phase 62/62B truth-gated selection and blocked-risk preservation.
3. Phase 63 embodiment/privacy eligibility adapters.
4. Phase 64 prompt preflight and Phase 65 packet-local safety metadata.
5. Phase 66 source-kind safety contracts.
6. Phase 67-73 handoff, dry-run, verifier, adapter, compliance, preview, and blueprint contracts.
7. Phase 74 audit receipt / attestation.
8. Phase 75 static prompt-boundary guardrails and Phase 76 adversarial coverage.
9. Phase 77 policy decision and Phase 78 operator review receipt.
10. Phase 79 synthetic-only harness.
11. Phase 80 internal no-LLM prompt candidate.
12. Phase 81 internal display receipt.
13. Phase 82 model-call preflight.
14. Phase 83 model-call review receipt.

## Dry-run Envelope Is Not Provider Invocation

The envelope is a request-shaped audit artifact only. It copies the Phase 80 candidate text into `dry_run_prompt_text` solely under non-sendable markers and binds all prerequisite IDs/digests. It does not provide a transport, client, endpoint, credential, provider parameter object, executable callback, tool definition, memory handle, action handle, retention handle, or routing handle.

## Provider/model Label-only Behavior

Provider families are metadata-only labels:

- `provider_family_openai_label_only`
- `provider_family_local_label_only`
- `provider_family_unknown_forbidden`

Model families are metadata-only labels:

- `model_family_reasoning_label_only`
- `model_family_chat_label_only`
- `model_family_unknown_forbidden`

Unknown labels block the dry run. Known labels do not instantiate SDKs or authorize egress.

## Non-sendable Markers

Every ready envelope must preserve explicit true markers including:

- `provider_dry_run_only`
- `non_sendable`
- `provider_send_forbidden`
- `network_egress_forbidden`
- `credentials_forbidden`
- `provider_client_absent`
- `endpoint_absent`
- `api_key_absent`
- `tool_calls_forbidden`
- `memory_forbidden`
- `retention_forbidden`
- `action_execution_forbidden`
- `routing_forbidden`
- `does_not_call_llm`
- `does_not_send_to_provider`
- `does_not_retrieve_memory`
- `does_not_write_memory`
- `does_not_trigger_feedback`
- `does_not_commit_retention`
- `does_not_execute_or_route_work`
- `does_not_admit_work`

Any false required marker blocks the envelope.

## Payload Shape Rules

The payload uses only dry-run labels such as `dry_run_internal_candidate`, `dry_run_boundary_notes`, and `dry_run_caveats`. It may include the non-sendable dry-run prompt text, digest references, and metadata tags. It must not include provider roles, endpoint fields, credentials, auth headers, clients, sessions, tool schemas, function definitions, raw payloads, provider parameters, or runtime handles.

## Credential/network/provider-client Forbidden Rules

The builder and validators block credential-like, endpoint/network-like, provider-client/session/transport-like, raw-payload, provider/model/LLM parameter, and runtime-authority markers in metadata and payload shape fields. These checks are deterministic and local; they do not import provider SDKs or inspect remote state.

## Digest Behavior

`compute_provider_dry_run_digest(...)` hashes stable envelope-safe fields only. The digest changes when linked candidate/display/preflight/review digests change, provider/model labels change, request purpose changes, dry-run prompt text changes, metadata parameters change, findings change, warnings change, constraints change, or boundary markers change. It excludes credentials, endpoints, provider clients, transport handles, runtime handles, nondeterministic timestamps, and raw payloads.

## Guardrail Behavior

The Phase 75 static verifier now scans `prompt_provider_dry_run.py`, permits `dry_run_prompt_text` only in the provider dry-run module and its Phase 84 test, and continues to reject final prompt text, assembled prompt names, raw payload fields, provider parameters, credentials, endpoints, auth/header fields, clients, sessions, tool-call markers, forbidden runtime imports, provider calls, network calls, memory calls, action calls, retention calls, routing/admission calls, and `assemble_prompt(...)` calls.

## Tests

Phase 84 tests cover successful ready envelopes, warning status propagation, missing or invalid reviews, denied preflights, blocked candidates, denied displays, unknown labels, forbidden scopes, credential/network/client markers, false non-sendable markers, runtime markers, payload shape restrictions, non-sendability helpers, deterministic digest behavior, input immutability, runtime-call absence, blocked/adversarial upstream evidence, guardrail allow/reject behavior, and import purity.

## Deferred Work

Future phases may add provider-call simulation or egress review, but only after this non-sendable envelope remains green under the guardrails. Any future phase must add a separate gate and must not reinterpret Phase 84 as provider invocation authority.
