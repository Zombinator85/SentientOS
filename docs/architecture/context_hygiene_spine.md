# Context Hygiene Spine

## Separation Contract
- Memory is durable historical substrate.
- Context is bounded, scoped, and temporary selection.
- Truth is adjudicated elsewhere and is not implied by inclusion in context.

## Why Context Packets Exist
Context packets provide an immutable-ish, typed boundary for selected references used in response construction without changing runtime behavior in this phase.

## Non-Authoritative Invariants
- Context packets are non-authoritative.
- Decision power is always `none`.
- Packets do not write memory.
- Packets do not admit, execute, or route work.
- Inclusion and exclusion reasons are retained.
- Validity bounds are mandatory.
- Included references require provenance.

## No Raw Memory Dump Invariant
The schema intentionally separates memory/claim/evidence/stance/diagnostic/embodiment lanes and does not expose any raw memory dump lane.

## Future Integration Points
- **Truth spine:** contradiction/freshness/provenance statuses are explicit and can be consumed by future truth adjudication.
- **Embodiment ladder:** embodiment references are isolated in a dedicated lane for future governed fusion.

## Deferred Work
- Selector
- Distiller
- Pruner
- Prompt adapter / runtime middleware


## Phase 62: Truth-Gated Context Selector Alpha

Phase 62 adds a pure selector layer that evaluates normalized candidates before prompt use. The selector is non-authoritative and returns a Phase 61 `ContextPacket` only.

Key assertions:
- Truth validation is not automatic inclusion.
- Relevance is not equivalent to truth.
- Exclusion reasons are mandatory for every dropped candidate.
- Embodiment privacy/sanitization policy remains deferred to Phase 63 (raw embodiment candidates are excluded by default).


## Phase 62B risk-contract alignment
- `PollutionRisk` supports `low|medium|high|blocked`.
- `blocked` is distinct from `high`: blocked means ineligible for active lanes; high means eligible with caution.
- Packet pollution risk is an assembly-level aggregate over attempted candidates, not only included lanes.
- If any attempted candidate is blocked, packet risk is `blocked` and blocked candidates remain visible in `excluded_refs`/`exclusion_reasons`.
- `provenance_complete` reflects all attempted candidates; included refs remain provenance-bearing.
- This lands before Phase 63 so privacy/embodiment blocked states are preserved instead of silently degrading to `high`.


## Phase 63: Embodiment/Privacy Context Eligibility Bridge
- Raw perception is not context.
- Sanitized embodiment summaries may become context candidates.
- Privacy-sensitive, biometric/emotion-sensitive, raw-retention, and action-capable material is blocked unless explicitly sanitized and allowed.
- This phase is adapter/eligibility only: not prompt assembly, not memory write, and not embodiment runtime behavior.

## Phase 64: Prompt-Eligibility Preflight Contract
- Phase 64 introduces prompt preflight before any prompt-assembly wiring.
- Selection is not prompt eligibility.
- `blocked` packet risk prevents prompt eligibility.
- `high` risk may be prompt-eligible only with explicit caveats.
- Phase 64 does not assemble prompts.
- Phase 64 does not call LLMs.
- Phase 64 does not retrieve or write memory.
- Phase 64 does not modify embodiment, action, or retention runtime behavior.

## Phase 65: Context Safety Metadata Preservation
- ContextPacket lane refs preserve compact packet-safe `context_safety_metadata` evidence for preflight/diagnostics.
- Packets remain auditable without raw-source rehydration.
- Preserved metadata is non-raw and non-authoritative; no prompt assembly/LLM/retrieval/memory-write/runtime action behavior is added.
- This closes the Phase 64 metadata-loss blind spot between selector and prompt preflight.


## Phase 66: Source-kind safety contract matrix
- Safety metadata must be source-kind complete for contract-required kinds.
- Explicit `unknown` source kind fails closed where contracted safety metadata is required.
- Contracts validate evidence metadata only (non-authoritative) and do not grant authority.
- No prompt assembly, LLM calls, retrieval, memory writes, or runtime embodiment/action/retention behavior changes are introduced in this phase.


## Phase 67: Context Prompt Handoff Manifest
- Adds pure manifest contract artifact before any prompt assembly wiring.
- Records eligible/caveated/blocked handoff posture from packet + preflight.
- Does not contain prompt text or call LLM/web/retrieval/memory write paths.
- Preserves packet-safe summaries, lane/ref summaries, and safety metadata summaries only.
- Does not alter embodiment/action/retention runtime behavior.

## Phase 68: Prompt Assembly Dry-Run Envelope
- Adds a pure dry-run envelope sourced only from the Phase 67 handoff manifest.
- Maps handoff status to dry-run readiness without assembling prompt text.
- Carries manifest id/digest, packet id/scope, assembly constraints, section summaries, and safe admissible ref summaries only for ready/caveated manifests.
- Withholds admissible refs for blocked, not-applicable, and invalid manifests while preserving block reasons, caveats, source-kind summary, safety-contract gap summary, and provenance summary.
- Includes explicit no-runtime markers for no LLM calls, memory retrieval/writes, feedback, retention, work routing/execution/admission, or final prompt text.

## Phase 69: Prompt Assembly Constraint Verifier
- Adds a pure verifier for hypothetical future prompt assembly candidate plans against the Phase 68 dry-run envelope.
- Proves future assembler inputs use only admissible refs, preserve caveats, preserve provenance/privacy/truth/safety boundaries, and retain no-runtime constraints.
- The candidate plan is not prompt text and the verifier does not assemble prompts.
- The verifier does not call LLMs, web clients, or retrieval paths.
- The verifier does not retrieve or write memory.
- The verifier does not modify truth, embodiment, action, retention, routing, orchestration, admission, or execution runtime behavior.
- Blocked, not-applicable, and invalid envelopes admit no candidate refs while preserving diagnostic caveats, constraints, and block posture for review.

### Phase 70: Prompt Assembly Adapter Contract

Phase 70 adds `sentientos.context_hygiene.prompt_adapter_contract` as a dry-wired adapter contract between the Phase 69 constraint verifier and any future prompt assembler. The adapter defines the future prompt-assembler-facing payload shape while remaining non-authoritative and preparation-only.

The adapter does not modify `prompt_assembler.py`, does not assemble prompts, does not contain final prompt text, does not call LLMs, and does not retrieve or write memory. It also does not change truth, embodiment, action, retention, routing, admission, execution, or orchestration runtime behavior. Adapter refs are gated by Phase 69 verification status, and failed, not-applicable, invalid, or blocked material is withheld from adapter refs while warnings and violations remain visible.

### Phase 71: Prompt Assembler Compliance Harness

Phase 71 adds `sentientos.context_hygiene.prompt_assembler_compliance` as a pure compliance harness for future prompt assembler integration requirements. It evaluates Phase 70 adapter payload readiness, records gaps/warnings/non-runtime markers, and statically scans `prompt_assembler.py` using source text/AST inspection only.

The compliance harness defines future prompt assembler rules: adapter payloads must be verified before use, only adapter refs may be consumed, failed/blocked/invalid/not-applicable payloads must not produce prompt material, and caveat/provenance/privacy/truth/safety boundaries must remain visible.

Phase 71 does not modify `prompt_assembler.py`, does not wire adapter payloads into it, does not assemble prompts, does not call LLMs, does not retrieve or write memory, and does not modify embodiment, action, retention, truth, routing, admission, execution, or orchestration runtime behavior.

### Phase 72: Prompt Assembler Shadow Adapter Hook

Phase 72 adds the first controlled `prompt_assembler.py` context hygiene touch: a shadow-only adapter preview hook that validates a Phase 70 `PromptAssemblyAdapterPayload` through the Phase 71 compliance harness. The hook exists in `prompt_assembler.py` so the prompt assembler can recognize the adapter contract, but it is opt-in and test-invoked only in this phase.

The hook is not used by runtime prompt assembly paths. It does not alter `assemble_prompt(...)`, does not change existing call sites, does not assemble prompt text, and does not concatenate adapter refs into final prompt material. Its output is a compact preview/receipt containing adapter/compliance status, metadata counts, caveats, notes-presence booleans, warnings, violations, constraints, rationale, and explicit non-runtime markers.

Phase 72 does not call LLMs, does not retrieve memory, does not write memory, and does not modify truth, embodiment, action, retention, routing, admission, execution, or orchestration runtime behavior. Blocked, not-applicable, invalid, or runtime-wiring-detected adapter payloads remain prompt-materialization blocked and expose only preview status/metadata for audit.

### Phase 73: Prompt Assembler Shadow Blueprint Contract

Phase 73 adds a second controlled `prompt_assembler.py` context hygiene touch: a shadow-only blueprint helper that converts a Phase 70 `PromptAssemblyAdapterPayload`, after Phase 72 shadow preview and Phase 71 compliance, into a structured future prompt-layout blueprint. The blueprint groups compliant adapter refs into blueprint sections and records caveat, provenance, privacy, truth, safety, constraint, status, and digest metadata.

The blueprint is test-invoked only and is not live prompt assembly. It does not assemble prompt text, does not concatenate adapter refs into prompt prose, does not call LLMs, does not retrieve memory, and does not write memory. Blocked, not-applicable, invalid, or runtime-wiring-detected payloads produce no blueprint refs and keep prompt materialization blocked.

Phase 73 does not modify truth, embodiment, action, retention, routing, admission, execution, or orchestration runtime behavior. It does not alter existing `assemble_prompt(...)` behavior or any existing call site.

## Phase 74: Prompt Materialization Audit Receipt / Attestation
- Adds a pure audit receipt artifact that binds manifest/envelope/verifier/adapter/compliance/preview/blueprint evidence into one deterministic attestation.
- The receipt is not prompt materialization and does not assemble prompt text.
- The receipt does not call LLMs, retrieve memory, write memory, or modify embodiment/action/retention runtime behavior.
- The receipt preserves IDs, digests, statuses, caveats, warnings, violations, boundary markers, provenance/privacy/truth/safety summaries, source-kind/ref/section counts, and a deterministic receipt digest.
- The receipt is the prerequisite gate for any future shadow text materializer; blocked, not-applicable, invalid, invalid-chain, and runtime-wiring statuses remain non-materializable.

## Phase 75: Context Hygiene Prompt Boundary CI Guardrails
- Adds static/CI guardrails for the context-hygiene prompt assembly boundary before any future prompt text materialization is allowed.
- The guardrails inspect source text and AST only; they are not prompt materialization and do not assemble prompt text.
- The guardrails enforce forbidden prompt-text fields, raw-payload/runtime-handle fields, forbidden runtime imports, forbidden runtime calls, and prompt-assembler bypass imports.
- The guardrails do not call LLMs, provider SDKs, web clients, tools, browser controllers, or hardware adapters.
- The guardrails do not retrieve memory, write memory, trigger feedback, commit retention, admit work, route work, execute work, or orchestrate runtime behavior.
- The guardrails do not modify truth, embodiment, action, retention, routing, admission, execution, orchestration, or live `assemble_prompt(...)` behavior.
- Phase 75 preserves the Phase 72-74 shadow-only allowlist while continuing to require no-runtime markers and no forbidden calls/imports inside those implementations.
- These guardrails are prerequisite enforcement before any future synthetic materializer may be proposed.

## Phase 76: Context Hygiene Adversarial Failure-Mode Harness
- Adds deterministic adversarial and property-style tests for the Phase 61-75 shadow prompt assembly runway.
- Covers prompt injection metadata, raw payload smuggling, capability smuggling, runtime-authority booleans, blocked/excluded/unknown ref smuggling, digest and identity mismatches, warning/caveat/violation/note downgrades, and runtime-call sentinels.
- The harness does not materialize prompt text and does not assemble final prompts.
- The harness does not call LLMs, provider SDKs, web clients, tools, browser controllers, hardware adapters, or live `assemble_prompt(...)` behavior.
- The harness does not retrieve memory, write memory, trigger feedback, commit retention, route work, admit work, execute work, or orchestrate runtime behavior.
- The harness does not modify truth, embodiment, action, retention, routing, admission, execution, orchestration, or embodiment runtime behavior.
- Phase 76 is a prerequisite before any future synthetic materializer because it proves adversarial metadata fixtures are blocked or withheld before prompt materialization exists.

## Phase 77: Context Hygiene Policy Decision Layer

Phase 77 adds `sentientos.context_hygiene.prompt_materialization_policy` as a pure policy decision layer over the Phase 61-76 prompt assembly runway. It consumes Phase 74 audit receipt metadata, Phase 73 blueprint status, preview/compliance/adapter evidence, source-kind summaries, caveats, warnings, violations, findings, feature flags, and operator-review state to decide whether a future materializer posture is denied, shadow-only, operator-review-required, or synthetic-fixture-only eligible.

The Phase 77 policy decision layer is not enforcement and is not prompt materialization. It does not assemble prompts, does not contain final prompt text, does not call LLMs, does not retrieve or write memory, does not trigger feedback, does not commit retention, does not execute or route work, and does not admit work. It does not modify truth, embodiment, action, retention, routing, admission, execution, orchestration, or live `assemble_prompt(...)` behavior.

Live/internal/LLM-capable rings remain forbidden in Phase 77. `ring_internal_candidate_no_llm` and `ring_live_llm_forbidden` are declared only so the policy can deterministically deny them.

## Phase 78: Operator Review Receipt Contract

Phase 78 adds `sentientos.context_hygiene.prompt_operator_review` as a deterministic, metadata-only operator review receipt contract for Phase 77 policy decisions that require review. Operator review receipts can satisfy review-required warnings and caveats only; they do not grant runtime authority and are not prompt materialization.

The review receipt cannot override hard policy denial, blocked refs, raw payload markers, prompt text markers, missing provenance, digest mismatch, runtime authority, action/retention/memory/tool capability, unknown source kinds, or live/internal/LLM-capable rings. If an acceptance decision attempts to attach operator review to those hard-block conditions, the receipt records `review_forbidden_override_attempted` and cannot satisfy the policy decision.

The receipt preserves digest linkage to the Phase 77 policy decision and Phase 74 audit receipt, reviewer metadata, accepted/rejected warning and caveat codes, required warning and caveat codes, expiration metadata, findings, and explicit non-runtime markers. It does not materialize prompt text, assemble prompts, call LLMs, retrieve memory, write memory, trigger feedback, commit retention, execute or route work, admit work, or modify embodiment/action/retention runtime behavior.

## Phase 79 — Synthetic-only prompt candidate harness

Phase 79 introduces `sentientos.context_hygiene.prompt_synthetic_materializer` as a deterministic fixture-only harness for prompt-shaped formatting tests. It may render `SYNTHETIC FIXTURE ONLY` candidate text from explicitly synthetic refs and sections only after the Phase 74 audit gate, Phase 77 synthetic fixture policy gate, and Phase 78 operator review gate (when required) are satisfied.

This phase is not live prompt materialization and is not real context materialization. Real context remains forbidden, `prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched, LLM calls remain forbidden, memory retrieval and writes remain forbidden, and embodiment/action/retention/routing/admission/execution/orchestration runtime behavior remains forbidden.

The harness exists solely to preserve formatting boundaries, caveats, and untrusted/reference-only labels with synthetic fixtures before any future internal no-LLM candidate path is considered. Any later candidate path must treat Phase 79 as a prerequisite formatting harness, not as runtime authority.

## Phase 80: Internal No-LLM Prompt Candidate Contract

Phase 80 adds the first narrow internal real-context candidate path. It may render operator-visible prompt-shaped candidate text from approved, packet-safe context hygiene summaries only, after the Phase 74 audit receipt, Phase 77 policy decision, and Phase 78 operator review gates pass.

The Phase 80 candidate is not an LLM invocation and is not live prompt assembly. LLM calls remain forbidden, `assemble_prompt(...)` remains untouched, and memory retrieval/writes remain forbidden. Embodiment runtime effects, actions, retention, routing, admission, execution, fulfillment, and orchestration remain forbidden.

All rendered context is explicitly marked untrusted/reference-only and cannot become system or developer instruction authority. Caveats, boundary notes, and provenance summaries remain visible in the internal candidate text. Phase 80 is a prerequisite contract for any later model-call or live user-facing phase, not that later phase itself.

## Phase 81: Internal Candidate Display Receipt / Egress Boundary

Phase 81 adds `sentientos.context_hygiene.prompt_internal_display` as an internal display/egress receipt layer for Phase 80 `InternalPromptCandidate` objects. It controls whether already-rendered internal candidate text may be shown to an operator-only internal review/debug/audit surface.

The display receipt is not UI and is not model egress. It does not duplicate the full Phase 80 `internal_candidate_text` by default; it records only candidate text digest, candidate text length, redaction state, and deterministic receipt metadata. Future display code must validate the receipt and then read text from the original candidate if display is permitted.

Allowed display scopes are limited to `operator_internal_review`, `operator_internal_debug`, and `audit_replay`. External-user-visible display, model/provider egress, tool/action egress, unknown scopes, missing operator references, expired receipts, digest mismatches, blocked/invalid/policy-denied/review-required candidates, runtime authority, raw payload markers, and provider parameter markers deny display.

No LLM/model/provider egress remains allowed. `prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched. Memory retrieval/writes, feedback, retention, embodiment runtime effects, actions, routing, admission, execution, fulfillment, and orchestration remain forbidden.

Phase 81 is a prerequisite metadata gate for any future internal review or internal model-call review gate. It grants no runtime authority by itself.

## Phase 82: Internal Model-Call Preflight Contract

Phase 82 adds `sentientos.context_hygiene.prompt_model_call_preflight` as a deterministic, metadata-only preflight artifact for deciding whether a Phase 80 `InternalPromptCandidate`, a Phase 81 display receipt, a Phase 77 policy decision, a Phase 74 audit receipt, and optional Phase 78 operator review evidence may be considered for a future internal model-call review gate.

The preflight is not model invocation. It does not call LLMs, does not send candidate text to providers, does not add provider SDK imports, does not retrieve memory, does not write memory, does not trigger feedback, does not commit retention, does not execute tools/actions, and does not route, admit, fulfill, or orchestrate work.

Phase 82 declares metadata-only rings: `model_review_preflight_only`, `internal_model_call_review_queue`, `internal_model_call_dry_run_forbidden_provider`, and `live_model_call_forbidden`. Only the preflight/review-queue rings can yield review eligibility; the dry-run provider ring remains provider-forbidden and the live ring always denies. No Phase 82 status permits a provider call.

`prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched. Memory retrieval/writes remain forbidden, embodiment/action/retention/routing/admission/execution runtime behavior remains forbidden, and operator display scope remains internal operator/debug/audit only.

Phase 82 is a prerequisite to any future internal provider dry-run or model-call review gate. It grants no runtime authority and produces only eligibility status, reasons, mitigations, digest linkage, provider-absence proof, no-tool/no-memory/no-retention/no-action constraints, and explicit denial/default-block markers.

## Phase 83: Internal Model-Call Review Receipt Contract

Phase 83 adds `sentientos.context_hygiene.prompt_model_call_review` as a deterministic, metadata-only review receipt layer for Phase 82 `InternalModelCallPreflight` decisions. It records operator reviewer identity, decision, scope, approved/rejected constraints, required/accepted/rejected mitigations, expiration, findings, digest linkage, and explicit non-runtime markers.

The model-call review receipt is not model invocation and is not provider egress. It can approve only a future internal model-call review gate as metadata; it can never approve provider invocation in Phase 83. `provider_dry_run_future_gate` remains constrained and future-phase-only, while live provider call, tool/action, and external-user-visible scopes remain non-overridable.

Provider calls and LLM calls remain forbidden. The receipt stores false provider/LLM/tool/memory/action/retention/routing allowances and true `provider_call_forbidden`, `llm_call_forbidden`, `does_not_call_llm`, and `does_not_send_to_provider` markers. Memory retrieval and writes remain forbidden. Feedback, retention, embodiment runtime effects, actions, routing, admission, execution, fulfillment, and orchestration remain forbidden.

`prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched. Phase 83 is a prerequisite attestation layer for any future provider dry-run contract, not that future contract and not a runtime model-call path.

## Phase 84: Provider Dry-Run Request Envelope — No Send

Phase 84 adds `sentientos.context_hygiene.prompt_provider_dry_run` as a deterministic provider-shaped dry-run request envelope. It binds a Phase 80 `InternalPromptCandidate`, Phase 81 internal display receipt, Phase 82 model-call preflight, and Phase 83 model-call review receipt into a single non-sendable artifact for internal review.

The provider dry-run envelope is not provider invocation. Provider and model families are label-only metadata, not SDK clients, transports, endpoints, or deployable provider parameters. The dry-run payload uses dry-run-only labels and explicitly marks provider sends, network egress, credentials, provider clients, tool calls, memory, retention, action execution, routing, admission, LLM calls, and provider egress as forbidden.

Provider/LLM calls remain forbidden. The module imports no provider SDKs or network clients and performs no network calls. It does not retrieve memory, write memory, trigger feedback, commit retention, execute tools/actions, route/admit/fulfill/orchestrate work, or invoke embodiment runtime behavior.

`prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched. Phase 84 is a prerequisite evidence artifact for any future provider-call simulation or egress review phase; it grants no runtime authority and cannot be used as a sendable request.

## Phase 85: Provider Dry-Run Egress Review Receipt

Phase 85 adds `sentientos.context_hygiene.prompt_provider_dry_run_review` as a deterministic, metadata-only egress review receipt for Phase 84 `ProviderDryRunRequestEnvelope` artifacts. It records reviewer identity, decision, scope, approved/rejected constraint codes, required/accepted/rejected mitigation codes, expiration, findings, digest linkage, and explicit non-sendable/provider-forbidden markers.

The dry-run egress review can approve only a future provider-call simulation gate or a future egress-review gate. It can never approve actual provider send, network egress, provider SDK/client use, credential use, endpoint use, tool calls, memory retrieval/writes, feedback, retention, embodiment runtime effects, actions, routing, admission, execution, fulfillment, or orchestration.

Provider/LLM/network calls remain forbidden. Credentials, provider clients, transports, endpoints, and deployable provider parameters remain forbidden. `prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched. Memory retrieval and writes remain forbidden, and embodiment/action/retention/routing/admission/execution runtime behavior remains forbidden.

The receipt derives required mitigations from Phase 84 findings, warnings, constraints, warning status, and provider/network/credential/client forbidden markers. A receipt satisfies an envelope only when the envelope is ready or ready-with-warnings, the receipt is approved or approved-with-constraints, ids and digests match, the receipt is unexpired, required mitigations are accepted or addressed, no forbidden send override is attempted, all runtime/provider allowances remain false, and all non-sendable markers remain true.

Phase 85 is a prerequisite to any future provider-call simulation contract or egress-review gate. It is not provider invocation and grants no runtime authority.

## Phase 86 — Provider Simulation Result Envelope (No Network)

Phase 86 adds `sentientos.context_hygiene.prompt_provider_simulation`, a pure provider simulation result envelope for Phase 84 provider dry-run requests after Phase 85 egress review approval. The artifact is fixed-stub/metadata-only and exists to record a deterministic provider-like boundary without provider invocation.

The Phase 86 envelope preserves these boundaries:

- provider/LLM/network calls remain forbidden;
- credentials, provider clients, endpoints, auth/header material, SDK objects, sessions, transports, streams, and runtime handles remain forbidden;
- semantic generation remains forbidden, and the simulated result stub must not answer, summarize, transform, or complete prompt content;
- live `assemble_prompt(...)` behavior is untouched, and `prompt_assembler.py` remains outside this phase;
- memory retrieval and memory writes remain forbidden;
- embodiment runtime, tools, actions, retention, feedback, routing, admission, execution, fulfillment, and orchestration remain forbidden.

Phase 86 is a prerequisite artifact for any future network-egress preflight or provider-call harness, but it does not authorize or implement those future paths. Provider simulation is not provider invocation.

## Phase 87: Provider Simulation Network-Egress Preflight

Phase 87 adds `ProviderNetworkEgressPreflight`, a deterministic audit/preflight artifact that binds the Phase 84 provider dry-run request envelope, Phase 85 provider dry-run egress review receipt, and Phase 86 provider simulation result envelope into a single future-review decision. Network-egress preflight is not network egress: provider calls, LLM calls, network calls, credentials, provider clients, sessions, transports, endpoints, and authorization material remain forbidden.

The Phase 87 artifact records digest-chain completeness, findings, warnings, required mitigations, no-runtime markers, and a compact rationale. It never performs semantic generation, never sends prompt text to a provider, never retrieves or writes memory, never commits retention, never executes embodiment/action/tool behavior, and never routes, admits, fulfills, or orchestrates work. Live `assemble_prompt(...)` behavior remains untouched.

Phase 87 is a prerequisite for any future network-egress review receipt or provider-call harness. Future phases may review its metadata, but Phase 87 itself grants no live provider-send, network-egress, credential-use, client-construction, model-call, action, retention, routing, admission, execution, or memory authority.

## Phase 88: Provider Network-Egress Review Receipt

Phase 88 adds `sentientos.context_hygiene.prompt_network_egress_review` as a deterministic, metadata-only review receipt for Phase 87 `ProviderNetworkEgressPreflight` artifacts. Provider network-egress review is not network egress. The receipt can approve only future metadata gates: a future network-egress review gate, a future provider-call dry-run gate, or a future null-transport adapter gate.

The receipt can never approve actual network egress or provider send. Provider SDKs, clients, sessions, transports, endpoints, credentials, authorization material, provider/LLM calls, network calls, semantic generation, tool calls, memory retrieval/writes, feedback, retention, embodiment runtime effects, actions, routing, admission, execution, fulfillment, and orchestration remain forbidden.

The Phase 88 receipt derives required mitigation codes from Phase 87 findings, warnings, required mitigations, review-required/ready-with-warnings statuses, and network/provider/credential/client/endpoint/semantic-generation/no-runtime constraints. A receipt satisfies a preflight only when IDs and digests match, the preflight is ready/review-required, the receipt is approved or constrained, unexpired, all required mitigations are accepted or addressed, no forbidden network override is attempted, all allowances remain false, and all no-network/provider-forbidden markers remain true.

`prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched. Phase 88 is a prerequisite evidence receipt for any future null transport adapter or provider-call dry-run contract, not that future contract and not a runtime network-egress path.

## Phase 89: Provider Null Transport Adapter Contract

Phase 89 adds `sentientos.context_hygiene.prompt_provider_null_transport` as a deterministic, metadata-only null transport adapter receipt for Phase 84 provider dry-run envelopes after Phase 87 network-egress preflight and Phase 88 review approval of `future_transport_null_adapter_gate`. The null transport adapter proves the transport boundary while sending nothing: null transport is not network transport.

The Phase 89 artifact records dry-run/preflight/review linkage, digest-chain completeness, no-send proof, no-network proof, credential/client/endpoint absence proof, findings, warnings, constraints, compact rationale, and explicit no-runtime markers. It never creates endpoint URLs, API keys, auth headers, provider clients, network sessions, HTTP requests, sockets, request/response handles, provider invocations, semantic outputs, model outputs, tool calls, or runtime side effects.

Provider, LLM, and network calls remain forbidden. Credentials, clients, endpoints, sockets, HTTP use, semantic generation, memory retrieval, memory writes, feedback triggers, retention commits, embodiment runtime effects, tools/actions, routing, admission, execution, fulfillment, and orchestration remain forbidden. `prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched.

Phase 89 is a prerequisite proof artifact for any future real network-egress contract. It grants no provider-send, network-egress, credential-use, client-construction, endpoint-use, socket/HTTP, model-call, semantic-generation, action, retention, routing, admission, execution, or memory authority.

## Phase 90: Provider Transport Registry Contract — Null-Only

Phase 90 adds `sentientos.context_hygiene.prompt_provider_transport_registry` as a deterministic, metadata-only provider transport registry and selector contract. The registry/selector exists to prove that transport selection is a governed boundary, but it allows only the Phase 89 `provider_transport_null_adapter` to be registered and selected.

Provider transport registry is not network transport. Real provider, OpenAI live, local model live, network, HTTP, socket, custom endpoint, SDK-backed, credentialed, endpoint, client/session, and live-send adapters remain forbidden, unregistered, and unselectable. Requested forbidden adapters produce deterministic forbidden/unregistered findings rather than runtime handles.

The Phase 90 selection receipt links the registry manifest to the Phase 89 null transport receipt and records registry/null/dry-run/network-preflight/network-review/candidate/packet audit-chain ids and digests. It proves `sent=False`, `bytes_sent=0`, no provider send, no network egress, no credentials, no endpoint, no provider client, no socket open, no HTTP request, no LLM call, no semantic generation, no tool call, no memory access, no retention, no action execution, no routing, no admission, and no runtime authority.

Provider/LLM/network calls remain forbidden. Credentials, clients, endpoints, sockets, HTTP use, semantic generation, model outputs, provider invocations, request/response handles, raw payloads, runtime handles, provider/model parameters, memory retrieval/writes, feedback triggers, retention commits, embodiment runtime effects, tools/actions, routing, admission, execution, fulfillment, and orchestration remain forbidden.

`prompt_assembler.py` and live `assemble_prompt(...)` behavior remain untouched. Phase 90 is a prerequisite metadata contract for any future real transport capability manifest or network-egress contract; it grants no provider-send, network-egress, credential-use, endpoint-use, client-construction, socket/HTTP, model-call, semantic-generation, action, retention, routing, admission, execution, or memory authority.
