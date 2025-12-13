## Degradation Contract

1. On any injected or detected failure, the active cycle stops immediately and emits one structured log entry on `sentientos.degradation`.
2. No retries, compensations, fallback goals, or continuation logic execute after the failure log.
3. Plan ordering, trust values, queues, and counters remain unchanged by the failed cycle.
4. Capability ledgers are never written during degradation handling; postmortems must use existing ledger state only.

What must never happen: recovery attempts, appetite synthesis, urgency bias, persistence bias, or reinterpretation of failure as a new goal.

Failure handling confirms degradation only; it is not a recovery attempt.

See also: NO_GRADIENT_INVARIANT, NAIR_CONFORMANCE_AUDIT, CAPABILITY_GROWTH_LEDGER.md (postmortem reference only).
