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
