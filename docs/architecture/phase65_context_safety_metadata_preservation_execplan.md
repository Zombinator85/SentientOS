# Phase 65: Context Safety Metadata Preservation

## Goal
Preserve compact non-raw context safety metadata from selector candidates into packet refs so packet-only preflight, diagnostics, and receipts remain auditable.

## Non-goals
No prompt assembly wiring, no memory writes, no action/retention/embodiment runtime behavior changes.

## Dependency chain
Phase 61 packet schema -> Phase 62 truth-gated selector -> Phase 62B blocked contamination -> Phase 63 embodiment/privacy eligibility -> Phase 64 preflight -> **Phase 65 packet-local metadata preservation**.

## Why packet-local metadata
Prompt preflight must evaluate risk/privacy/authority from packet refs without source rehydration.

## Evidence not authority
Safety metadata is bounded evidence only; it cannot grant execution, admission, routing, retention, or fulfillment authority.

## Preserved metadata
`source_kind`, `privacy_posture`, sanitization/eligibility markers, contradiction/freshness/provenance/risk posture, action/authority boundary booleans, and phase-63 non-effect guard flags.

## Never preserved
Raw perception/embodiment payloads, raw memory payloads, runtime handles, LLM prompts, retrieval handles, hardware/browser controls.

## Selector behavior
Selector copies normalized allowlisted safety metadata into packet ref provenance envelope and fails closed for required missing/unknown embodiment source kind metadata.

## Validation behavior
Packet validation rejects included refs with raw-source, action-capable, or authority-risk metadata; preserves legacy compatibility for non-embodiment refs without safety envelope.

## Preflight relationship
Preflight reads packet safety envelope first and blocks/caveats accordingly.

## Receipt behavior
Receipts were unchanged; they already preserve packet-level pollution/provenance/exclusion summaries and do not serialize raw payloads.

## Tests
Added Phase 65 contract tests for selector preservation, fail-closed behavior, validation blocks, preflight-from-packet behavior, and helper purity.

## Deferred work
Optional future tightening for non-embodiment lanes requiring richer safety envelope by source taxonomy versioning.
