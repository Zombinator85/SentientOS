# SentientOS Operator Handbook (Closure Wing)

## What kind of system is this?
SentientOS is a deterministic task-execution and audit framework. It ingests operator-defined tasks, gates them through admission policies, produces bounded outputs, and records evidence in append-only logs. It is not an autonomous agent, not a learner, and not a moral actor. The system’s guarantees are architectural: read-only observability, explicit consent gates, deterministic recovery ladders, and invariant-bound memory economics.

## What does refusal mean?
Refusal is a formal, structured outcome. The system declines when an invariant would be violated, when consent is missing, when recovery eligibility is disallowed, or when admission policies reject a task. A refusal is not a suggestion; it is a declared boundary recorded in diagnostics and logs.

## When the system says no, what should I infer?
A “no” indicates at least one of the following:
- A constitutional invariant blocks the action (e.g., consent required, recovery forbidden).
- An admission or authority policy gate denied the request.
- An explicit boundary (forgetting, embodiment, or recovery) refused a transition.
- The request would violate deterministic or audit requirements.
Treat refusals as reliable guardrails, not as negotiation cues.

## What kinds of failures are benign vs. structural?
**Benign (expected, recoverable) failures**
- Optional dependency missing; capability isolation applied.
- Install-time missing directories corrected by recovery ladders.
- Read-only telemetry or rendering errors with no state change.

**Structural (non-recoverable) failures**
- Invariant violations (e.g., recovery recursion, silent deletion attempts).
- Consent gate failures for embodiment egress.
- Admission or authority surface inconsistency.
Structural failures require operator review and cannot be auto-recovered.

## What automation exists?
- Deterministic recovery ladders for narrowly scoped, allowed error codes.
- Read-only diagnostics and summaries.
- Simulation-only memory economics and embodiment validation.
- Append-only introspection and audit logging.

## What automation will never exist?
- Autonomous task admission or execution.
- Silent memory deletion or retroactive log mutation.
- Unbounded recovery recursion or self-healing that bypasses proofs.
- Real-world actuation without explicit adapter enablement and consent.

## How should I reason about consent, recovery, and embodiment?
- **Consent** is explicit, scoped, revocable, and time-bound. No default approvals exist.
- **Recovery** is finite, eligibility-gated, and proof-bearing. Recovery is never recursive and never emits recoverable errors.
- **Embodiment** is simulation-only by default; signals are contract-bound and incur memory cost. Real-world I/O requires explicit future adapters and consent.

## Stewardship mindset
Operate as an auditor and steward. Trust the invariant boundaries, verify logs, and treat every output as technical evidence rather than agency. Stewardship is preserving the constraints as much as running the system.
