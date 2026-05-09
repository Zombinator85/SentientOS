# Phase 88: Provider Network-Egress Review Receipt — No Network

## Goal

Add `sentientos.context_hygiene.prompt_network_egress_review` as a deterministic, metadata-only review receipt for Phase 87 `ProviderNetworkEgressPreflight` artifacts. The receipt records whether a reviewer approves, denies, expires, or constrains a future metadata gate.

Core invariant: **provider network-egress review is not network egress**.

## Non-goals

Phase 88 does not:

- call an LLM or send prompt text to any provider;
- import provider SDKs or network clients;
- make network calls;
- construct endpoint, client, session, credential, or transport objects;
- perform semantic generation;
- retrieve memory, write memory, trigger feedback, or commit retention;
- execute tools/actions;
- route, admit, fulfill, orchestrate, or execute work;
- modify `prompt_assembler.py` or live `assemble_prompt(...)` behavior.

## Dependency chain: Phase 61 through Phase 87

Phase 88 sits after the existing context-hygiene runway:

1. Phase 61 introduced context packets and assembly receipts.
2. Phase 62 and 62B added truth-gated selection plus first-class blocked-risk contamination.
3. Phase 63 added embodiment/privacy eligibility adapters.
4. Phases 64-76 added prompt preflight, packet-local safety metadata, source-kind contracts, handoff manifests, dry-run envelopes, constraint verification, adapter contracts, compliance/shadow/blueprint hooks, materialization audit receipts, static guardrails, and adversarial failure-mode tests.
5. Phase 77 added a pure policy decision layer.
6. Phase 78 added operator review receipts.
7. Phases 79-81 added synthetic-only candidates, internal no-LLM candidates, and internal display receipts.
8. Phases 82-83 added internal model-call preflight and review receipt contracts that still forbid provider invocation.
9. Phase 84 added a non-sendable provider dry-run request envelope.
10. Phase 85 added provider dry-run egress review receipts for future simulation/review gates only.
11. Phase 86 added a fixed-stub provider simulation result envelope with no network and no semantic generation.
12. Phase 87 added provider simulation audit/network-egress preflight metadata.
13. Phase 88 reviews Phase 87 metadata only and grants no runtime authority.

## Review receipt is not network egress

The receipt may approve only these future metadata gates:

- `future_network_egress_review_gate`
- `future_provider_call_dry_run_gate`
- `future_transport_null_adapter_gate`

It never approves actual network egress, provider send, endpoint use, credential use, provider SDK/client/session/transport use, LLM invocation, semantic generation, tool calls, memory operations, retention, action execution, routing, admission, execution, fulfillment, or orchestration.

## Review statuses and scopes

Statuses are compact deterministic strings:

- `network_egress_review_approved`
- `network_egress_review_approved_with_constraints`
- `network_egress_review_rejected`
- `network_egress_review_expired`
- `network_egress_review_invalid`
- `network_egress_review_forbidden_network_override_attempted`
- `network_egress_review_not_applicable`

Metadata-only scopes are:

- approvable: `future_network_egress_review_gate`, `future_provider_call_dry_run_gate`, `future_transport_null_adapter_gate`;
- forbidden/non-overridable: `actual_network_egress_forbidden`, `actual_provider_send_forbidden`, `credential_use_forbidden`, `provider_client_use_forbidden`, `endpoint_use_forbidden`, `tool_or_action_forbidden`, `external_user_visible_forbidden`.

Approving the future network-egress review gate yields `network_egress_review_approved`. Future provider-call dry-run and null-transport adapter gates yield `network_egress_review_approved_with_constraints` when all no-network/provider-forbidden markers remain true.

## Required mitigation behavior

Required mitigation codes are derived deterministically from Phase 87 metadata:

- preflight findings;
- warning text digests;
- preflight `required_mitigations`;
- review-required and ready-with-warnings statuses;
- network/provider/credential/client/LLM/semantic-generation forbidden markers;
- Phase 88 endpoint and no-runtime forbidden constraints.

A receipt satisfies a preflight only when all required mitigations are accepted or addressed by approved constraint codes and no required mitigation is rejected.

## Forbidden network override rules

Approval attempts become `network_egress_review_forbidden_network_override_attempted` when they try to approve hard-denied or invalid preflights, invalid dry-run/review/simulation chain states, credentials detected, network forbidden states, runtime authority, incomplete digest chains, unknown/live-send rings, forbidden scopes, prompt/raw/provider/network/runtime marker evidence, or any allowance flag set to true.

Missing reviewer identity, unknown decision/scope, missing linkage digest, missing preflight ID, digest mismatch, and malformed input are invalid rather than approvable.

## Network/provider/credential/client/endpoint constraints

The receipt always records and preserves:

- `network_egress_allowed=False`
- `provider_send_allowed=False`
- `credentials_allowed=False`
- `provider_client_allowed=False`
- `endpoint_allowed=False`
- `llm_call_allowed=False`
- `semantic_generation_allowed=False`
- tool/memory/retention/action/routing allowances as false

The explicit forbidden/no-side-effect markers remain true, including `network_egress_forbidden`, `provider_send_forbidden`, `credentials_forbidden`, `provider_client_forbidden`, `endpoint_forbidden`, `does_not_make_network_calls`, `does_not_send_to_provider`, and `does_not_call_llm`.

## Digest behavior

`review_digest` is deterministic over stable metadata-safe fields: linkage IDs/digests, preflight status and ring metadata, reviewer reference, decision, review scope, constraint and mitigation codes, expiration, expired flag, forbidden override flag, findings, rationale, allowance flags, and markers.

The digest excludes prompt text, raw payloads, credentials, endpoints, provider handles, network handles, runtime handles, LLM/provider params, and nondeterministic timestamps unless explicitly supplied as stable metadata.

## Guardrail behavior

The Phase 75 guardrail scanner includes `sentientos/context_hygiene/prompt_network_egress_review.py` in default scans. It rejects provider SDK imports, web/network clients, prompt assembler imports/calls, memory manager imports, action/retention/routing imports/calls, model/provider calls, network calls, and prompt materialization fields.

## Tests

`tests/test_phase88_provider_network_egress_review_receipt.py` covers construction, approval/constrained/rejection/expiration/invalid statuses, forbidden scopes, allowance overrides, mitigation satisfaction, digest determinism and digest sensitivity, preflight satisfaction, no mutation, no runtime-call sentinels, Phase 84-88 happy path, blocked/adversarial non-overridable markers, guardrail scanning, and import-purity-oriented module import checks.

## Deferred work

Any future null-transport adapter or provider-call dry-run contract must consume Phase 88 as metadata evidence only. Future work must still add its own no-network/no-provider/no-credential/no-client/no-endpoint boundaries and must not treat Phase 88 as live network or provider-send authorization.
