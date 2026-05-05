# Phase 63 Embodiment/Privacy Context Eligibility Bridge

## Goal
Add pure adapter/eligibility helpers that transform already-sanitized embodiment artifacts into `ContextCandidate` objects for Phase 62 selection while blocking unsafe/raw artifacts.

## Non-goals
- No prompt assembly wiring.
- No memory writes.
- No embodiment runtime changes.
- No truth/action/retention/admission/execution routing changes.

## Dependency chain
- Phase 61: ContextPacket schema/receipts.
- Phase 62: truth-gated selector.
- Phase 62B: first-class `PollutionRisk.BLOCKED` with attempted-candidate contamination.

## Eligibility rules
Implements deterministic blocking/eligibility for source-kind, sanitization, provenance, scope, privacy posture, action capability, and non-authoritative flags.

## Blocked vs high risk
- Blocked: raw perception, unknown, missing provenance/scope, decision power, non-allowed privacy/biometric/raw-retention/action-capable.
- High: explicitly allowed + sanitized privacy-sensitive, biometric/emotion-sensitive, or raw-retention summaries.

## Source kind mapping
Includes raw legacy artifacts, embodiment snapshot/receipt/proposal/review/handoff/bridge/fulfillment paths, and ingress validations.

## ContextCandidate lane mapping
- `embodiment_proposal_diagnostic` -> `diagnostic`.
- Other eligible embodiment artifacts -> `embodiment`.

## Tests
`tests/test_phase63_embodiment_context_eligibility.py` validates all Phase 63 eligibility rules and selector compatibility.

## Deferred work
Runtime wiring into upstream producers and prompt assembly remains deferred.
