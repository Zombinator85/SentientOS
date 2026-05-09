# Phase 87 Provider Simulation Network-Egress Preflight Execplan

## Goal

Phase 87 adds a deterministic Provider Simulation Audit Receipt / Network-Egress Preflight Contract. It binds the Phase 84 `ProviderDryRunRequestEnvelope`, the Phase 85 `ProviderDryRunEgressReviewReceipt`, and the Phase 86 `ProviderSimulationResultEnvelope` into one metadata-only decision artifact for a future network-egress review gate.

## Non-goals

Phase 87 is not network egress. It does not call an LLM, send prompt text to a model/provider, import provider SDKs, make network calls, create client/session/credential objects, retrieve or write memory, commit retention, execute tools/actions, route/admit/orchestrate work, or change live `assemble_prompt(...)` behavior.

## Phase 61 through Phase 86 dependency chain

Phase 87 depends on the context-hygiene spine established by Phases 61-86: packet schema and receipts, truth-gated selection, blocked-risk preservation, embodiment/privacy eligibility, prompt preflight, source-kind safety, handoff/dry-run/constraint/adapter/compliance/shadow contracts, materialization audit and guardrails, adversarial tests, policy/operator review, synthetic/internal candidate and display boundaries, internal model-call preflight/review, provider dry-run, provider dry-run egress review, and fixed-stub provider simulation.

## Network-egress preflight is not network egress

The preflight may record audit status, preflight status, digest-chain completeness, future-review eligibility, findings, warnings, mitigations, provider absence proof, credential absence proof, and no-runtime markers. It must not record endpoint URLs, API keys, authorization headers, provider clients, sessions/transports, actual requests/responses, provider invocations, semantic outputs, model outputs, tool calls, or runtime side effects.

## Statuses and rings

Statuses are deterministic and deny by default:

- `network_egress_preflight_denied`
- `network_egress_preflight_ready_for_review`
- `network_egress_preflight_ready_with_warnings`
- `network_egress_preflight_review_required`
- `network_egress_preflight_invalid_input`
- `network_egress_preflight_simulation_invalid`
- `network_egress_preflight_dry_run_invalid`
- `network_egress_preflight_review_invalid`
- `network_egress_preflight_credentials_detected`
- `network_egress_preflight_network_forbidden`
- `network_egress_preflight_runtime_authority_detected`

Rings are metadata-only:

- `network_egress_review_preflight_only`: may become ready for review when all gates pass.
- `future_network_egress_review_gate`: records review required; no network egress is permitted.
- `future_provider_call_dry_run_gate`: may be ready with warnings only while no-network/provider-forbidden markers remain true.
- `live_provider_send_forbidden`: always denies.

## Audit chain behavior

The audit chain captures available IDs and digests for the dry-run, egress review receipt, simulation, candidate, internal display receipt, internal model-call preflight, internal model-call review receipt, packet ID, and packet scope. `digest_chain_complete` is true only when required Phase 84/85/86 IDs and digests exist and the stored digests match deterministic recomputation/linkage expectations. Missing or mismatched upstream evidence becomes a deterministic finding rather than an invented digest.

## Provider/network absence proof

The module imports only dataclass/hash/json/typing utilities and context-hygiene contract helpers. It does not import provider SDKs, web clients, network clients, prompt assembler code, memory managers, action modules, retention modules, routing modules, or runtime orchestration surfaces. Outputs explicitly set provider, network, credential, client, LLM, semantic generation, tool, memory, retention, action, and routing allowances to false while preserving forbidden markers.

## Gating rules

The preflight denies or invalidates missing/not-ready dry-runs, non-sendable violations, missing/expired/mismatched/non-satisfying egress reviews, missing/not-ready simulations, simulations that fail to preserve the dry-run/review linkage, no-network proof failures, model-output proof failures, incomplete digest chains, unknown rings, disabled feature flags, credential/network/client/session/transport markers, forbidden allowance attempts, raw/runtime/model/provider parameter markers, `internal_only=False`, and any no-network/no-provider/no-runtime flag set false.

## Digest behavior

The preflight digest is deterministic over stable metadata: upstream digests, requested/effective ring, feature-flag-derived status/findings, audit chain, findings, warnings, mitigations, allowances, and no-runtime markers. It excludes raw payloads, credentials, endpoints, provider handles, network handles, runtime handles, provider parameters, model parameters, timestamps, and any nondeterministic runtime object.

## Guardrail behavior

`scripts/verify_context_hygiene_prompt_boundaries.py` scans the Phase 87 module by default. It fails the module if provider SDKs, web/network clients, prompt assembler imports/calls, memory/action/retention/routing code, provider APIs, network APIs, or runtime side-effect calls are introduced.

## Tests

`tests/test_phase87_provider_simulation_network_egress_preflight.py` covers valid ready/review/warning rings, denied rings, missing and invalid upstream artifacts, review and simulation linkage, no-network and non-semantic proof failures, digest-chain incompleteness/mismatch, feature flags, forbidden credential/network/provider/runtime markers, allowance attempts, no-runtime flags, output markers, helper predicates, deterministic digest changes, input immutability, guardrail scanning, blocked attempted candidates, and import-purity behavior.

## Deferred work

A future phase may add a separate network-egress review receipt or provider-call harness. That later phase must consume Phase 87 as evidence but must not reinterpret Phase 87 as permission for live network egress or provider send.
