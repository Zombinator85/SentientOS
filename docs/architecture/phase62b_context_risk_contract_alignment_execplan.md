# Phase 62B Context Risk Contract Alignment

## Goal
Preserve `blocked` as first-class `ContextPacket.pollution_risk` so attempted blocked candidates are not normalized to `high`.

## Non-goals
No prompt assembly wiring, no memory retrieval/runtime changes, no truth runtime changes, no embodiment ingress runtime changes, and no routing/execution/retention behavior changes.

## Phase 62 seam
Phase 62 could return `blocked` from pollution guard but packet schema only allowed low/medium/high, collapsing blocked into high.

## Chosen semantics
- Included lanes never contain blocked candidates.
- `packet.pollution_risk` is aggregate attempted-candidate risk.
- Any blocked attempted candidate yields packet-level `blocked`.
- Packet remains diagnostic/non-authoritative and not prompt-authoritative.

## Provenance semantics
- `provenance_complete` is computed across attempted candidates.
- Missing provenance candidates are excluded-only.
- Included refs remain provenance-bearing.

## Files changed
- `sentientos/context_hygiene/context_packet.py`
- `sentientos/context_hygiene/pollution_guard.py`
- `sentientos/context_hygiene/selector.py`
- `tests/test_phase61_context_packet_contract.py`
- `tests/test_phase62_context_truth_selector.py`
- `tests/test_phase62b_context_risk_contract_alignment.py`
- `docs/architecture/context_hygiene_spine.md`

## Tests
Phase61/62 + new Phase62B contract tests + architecture/integrity boundary checks.

## Deferred work
Prompt-eligibility gating at assembly/runtime boundary is deferred to Phase 63.
