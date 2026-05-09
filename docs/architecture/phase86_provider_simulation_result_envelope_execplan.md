# Phase 86 Provider Simulation Result Envelope Execplan

## Goal

Phase 86 adds a deterministic `ProviderSimulationResultEnvelope` for Phase 84 `ProviderDryRunRequestEnvelope` objects after Phase 85 provider dry-run egress review approval. The envelope is a provider-like response boundary artifact only: it records stable metadata, digest linkage, findings, constraints, warnings, and a fixed stub that proves no provider/model/network path ran.

## Non-goals

- No LLM call, provider send, provider SDK import, or network egress.
- No semantic answer generation, prompt transformation, assistant-like completion, or model-computed output.
- No credentials, endpoints, auth headers, provider clients, sessions, transports, streams, request IDs, or response handles.
- No memory retrieval/write, retention commit, feedback trigger, tool/action execution, routing, admission, fulfillment, orchestration, or embodiment runtime effect.
- No change to live `assemble_prompt(...)` behavior and no dependency on `prompt_assembler.py`.

## Dependency chain: Phases 61 through 85

Phase 86 sits after the context-hygiene spine that created packet schemas, truth-gated selection, contamination preservation, embodiment/privacy eligibility adapters, preflight gates, packet-local safety metadata, source-kind contracts, handoff/dry-run/constraint contracts, adapter/compliance/shadow preview contracts, materialization audit receipts, static guardrails, adversarial tests, policy decisions, operator review, synthetic/internal prompt candidates, display/egress receipts, model-call preflight/review receipts, Phase 84 non-sendable provider dry-run requests, and Phase 85 dry-run egress review receipts.

The Phase 86 builder requires:

1. a Phase 84 dry-run envelope in `provider_dry_run_ready` or `provider_dry_run_ready_with_warnings`, and
2. a Phase 85 review receipt that satisfies the dry-run envelope and approves only a future provider simulation gate or future egress review gate.

## Provider simulation is not provider invocation

The simulation envelope represents a provider-like result shape without any provider execution. It preserves the invariant: **provider simulation is not provider invocation**. All explicit markers state that provider send, network egress, provider clients, credentials, semantic generation, tools, memory, retention, routing, admission, execution, and feedback remain forbidden.

## Simulation modes and statuses

Allowed metadata-only modes:

- `simulation_mode_fixed_stub`
- `simulation_mode_echo_metadata_only`
- `simulation_mode_transport_shape_only`

Forbidden modes include unknown, semantic-generation, live-provider, and network dry-run modes.

Statuses are deterministic and compact:

- `provider_simulation_ready`
- `provider_simulation_ready_with_warnings`
- `provider_simulation_blocked`
- `provider_simulation_invalid_input`
- `provider_simulation_review_missing`
- `provider_simulation_dry_run_not_ready`
- `provider_simulation_network_forbidden`
- `provider_simulation_credentials_detected`
- `provider_simulation_runtime_authority_detected`
- `provider_simulation_semantic_generation_forbidden`

## Fixed-stub and non-semantic behavior

The simulated result stub is fixed and metadata-only. It includes the markers `PROVIDER SIMULATION RESULT`, `NO MODEL CALLED`, and `NO NETWORK EGRESS`, plus digest references and simulation mode. It does not include or transform the dry-run prompt, answer the user, summarize content, produce assistant-like text, expose chain-of-thought, or claim provider/model execution.

## Payload shape rules

The payload shape uses simulation-only labels such as `simulated_provider_stub`, `simulated_transport_metadata`, and `simulated_no_network_boundary`. Usage metadata is zero/`None` placeholder data. Digest references are preserved. Provider roles, generated message content, request IDs, completion IDs, endpoint fields, credential fields, auth/header fields, clients, sessions, streams, tool/function calls, raw payloads, and runtime handles remain forbidden.

## No-network, provider-client, and credential rules

The builder blocks unless dry-run and review gates are clean, simulation scope is internal only, no credential/network/provider-object/runtime markers are present, and all no-provider/no-network/no-runtime markers are true. Helper predicates expose proofs for no-network, not-model-output, no provider credentials, no runtime authority, and dry-run/review linkage preservation.

## Digest behavior

`simulation_digest` is deterministic over stable envelope-safe fields. It changes when dry-run digest, egress review digest, simulation mode, simulation scope, simulated stub, payload shape, findings, warnings, constraints, provider label, or model label changes. It excludes credentials, endpoints, provider client objects, transport handles, raw payloads, runtime handles, model/provider parameters, timestamps, and other nondeterministic/runtime-only data.

## Guardrail behavior

The Phase 75 prompt-boundary verifier now scans the Phase 86 module by default. It permits the Phase 86 `simulated_result_stub` field only in the provider simulation module and its test surface while continuing to reject prompt materialization fields, live prompt assembly, provider SDK imports, web/network clients, memory/action/retention/routing imports, `assemble_prompt(...)`, provider/network/runtime calls, raw payloads, credentials, endpoints, clients, sessions, headers/auth, and model/provider parameter fields.

## Tests

The Phase 86 test suite covers ready/warning/review-missing/rejected/expired/mismatched dry-run gates, blocked dry-run statuses, forbidden modes/scopes, credential/network/runtime markers, marker overrides, fixed-stub markers, non-semantic behavior, payload shape safety, helper strictness, deterministic digest changes, immutability of inputs, no runtime imports/calls, Phase 63-to-86 pass/fail chaining, Phase 62B/76 adversarial blocking, Phase 75 guardrails, and architecture/import-purity marker expectations.

## Deferred work

Future phases may add a network-egress preflight or provider-call harness. Phase 86 intentionally does not authorize, implement, or preview any live provider call path; it only creates a deterministic internal artifact that can be inspected before any future gate is designed.
