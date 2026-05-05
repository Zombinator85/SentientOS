# Phase 61 — Context Hygiene Spine Alpha Execplan

## Goal
Ship schema/contract/test foundations for non-authoritative context packets and append-only assembly receipts.

## Non-goals
- No runtime prompt assembly changes.
- No memory retrieval/retention changes.
- No truth, embodiment ingress, action routing, or execution semantic changes.

## Current Risks
- Packet validation currently returns errors (does not raise) and callers must enforce policy.
- Receipt append helper is local JSONL append and depends on filesystem guarantees.

## Files Changed
- `sentientos/context_hygiene/__init__.py`
- `sentientos/context_hygiene/context_packet.py`
- `sentientos/context_hygiene/receipts.py`
- `tests/test_phase61_context_packet_contract.py`
- `docs/architecture/context_hygiene_spine.md`
- `docs/architecture/phase61_context_hygiene_spine_alpha_execplan.md`
- `sentientos/system_closure/architecture_boundary_manifest.json`

## Schema Contract
Defines immutable dataclasses and explicit status enums for context hygiene, including validity bounds, provenance checks, safety invariants, and separate context lanes.

## Receipt Contract
Defines JSON-compatible assembly receipts keyed by packet id and appended to JSONL in append-only mode.

## Tests
- packet validation and invariants
- expiry/provenance handling
- append-only receipt behavior
- import purity constraints
- immutability behavior
- explicit status/lane support

## Deferred Phases
- governed packet selector
- freshness/contradiction downgrader
- runtime prompt adapter integration
- receipt attestation and cross-ledger indexing
