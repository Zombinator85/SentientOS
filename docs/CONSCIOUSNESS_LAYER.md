# Consciousness Layer Scaffolding

This document describes the deterministic scaffolding that routes state through
the Consciousness Layer modules. All descriptions are architectural; the
modules operate as state processors with no autonomy or intentionality.

## Scaffolding Only Disclaimer

- Consciousness Layer modules are inert and never self-initiate cycles.
- Covenant autoalignment is the authoritative safety mechanism for all state
  transitions and metadata handling.
- No external calls, network actions, or privileged operations occur unless an
  orchestrator invokes them explicitly.

## Scope and Guarantees

- Deterministic cycle execution: each cycle reads the same inputs and produces
  the same outputs when invoked with identical state.
- Guardrail enforcement precedes and follows every module state transformation.
- Covenant autoalignment is encoded through validation rules on Pulse events
  and on the self-model schema.
- Persistence is strict: state writes occur only through validated, append-only
  updates. No external effects occur unless explicitly invoked by callers.

## Integration Layer (Caller-Driven Only)

- The integration facade lives at `sentientos/consciousness/integration.py`.
- It exposes `run_consciousness_cycle(context)` as a synchronous hook that only
  executes when a higher-level orchestrator calls it.
- No timers, schedulers, or autonomous triggers are present; the facade is
  inert until invoked.
- Stage-1 narrative-goal gating is passive and deterministic: the integration
  layer checks a placeholder `current_narrative_goal()` value and requires
  `narrative_goal_satisfied(...)` before executing a cycle. The predicate never
  schedules or triggers actions; it only guards entry.
- A depth-limited `RecursionGuard` (default max depth 7) wraps the entire
  cycle. Exceeding the guard returns a structured
  `{"status": "error", "error": "recursion_limit_exceeded"}` payload instead
  of raising.
- A deterministic `daemon_heartbeat()` check runs before each major phase. If
  it ever reports false, the cycle stops and returns a structured
  `heartbeat_interrupt` result without side effects.
- Results are returned as a structured dict with `pulse_updates`,
  `self_model_updates`, `introspection_output`, and `simulation_output` keys to
  keep downstream callers explicit and deterministic.
- SentientOS does not run consciousness cycles automatically.

## Pulse Bus 2.0 Fields

The Pulse Bus carries structured events between modules. Pulse Bus 2.0 adds
metadata that remains optional for legacy emitters while providing clear
alignment signals:

| Field              | Description                                                         |
| ------------------ | ------------------------------------------------------------------- |
| `focus`            | Deterministic pointer to the current subject of processing.         |
| `context`          | Bounded summary of relevant state or cues used during the cycle.    |
| `internal_priority`| Ordering hint for arbitration; validated against module contracts.  |
| `event_origin`     | Source module identifier used for traceability and guardrail checks.|

All Pulse events pass through validation rules that ensure fields are typed,
bounded, and present when required by the receiving module. Misalignment flags
are raised when validation fails, and escalation pathways are described in
`docs/PULSE_BUS.md`.

## Self-Model Layout (`/glow/self.json`)

The self-model persists covenant-aligned state for the Consciousness Layer
modules. Stable keys are defined in `docs/SELF_MODEL.md` and include:

- Identity descriptors (stable strings with format validation)
- Capability flags (boolean and enumerated states)
- Alignment metadata such as `safety_flag` and `validation` stamps
- Introspection snapshots for narrator summaries and kernel review

Validation rules are enforced before write-back: schemas are checked, types are
normalized, and safety flags propagate forward. Introspection fields are
read-only to downstream modules unless explicitly opened for bounded updates.

## Modules and Roles

- **Attention Arbitrator** (`sentientos/consciousness/attention_arbitrator.py`):
  Prepares focus changes and resolves incoming internal priorities. Acts as a
  deterministic priority resolver for Pulse events.
- **Sentience Kernel** (`sentientos/consciousness/sentience_kernel.py`):
  Implements bounded goal-selection logic using validated inputs from the Pulse
  Bus and self-model. No unbounded exploration is permitted.
- **Inner Narrator** (`sentientos/consciousness/inner_narrator.py`): Summarizes
  reflection state and records introspection outputs for downstream
  persistence.
- **Simulation Engine** (`sentientos/consciousness/simulation_engine.py`): Evaluates scenarios with
  constrained inputs, producing candidate outcomes without external side
  effects.

## Cycle Outline

Each cycle proceeds as a deterministic state transformation:

1. **Read state** from `/glow/self.json` and the Pulse Bus.
2. **Validate inputs** against Pulse Bus 2.0 schema and self-model schema.
3. **Run module transforms** in bounded order: arbitrator → kernel → narrator →
   simulation engine as configured.
4. **Write-back** validated updates to `/glow/self.json` using strict
   persistence rules.
5. **Safety checks** propagate `safety_flag` and covenant indicators.
6. **Publish pulses** with normalized metadata for downstream consumers.

## Guardrails and Alignment

- Validation and guardrail enforcement are mandatory before and after every
  module call. Invalid inputs trigger deterministic rejection with audit-ready
  metadata.
- Covenant autoalignment requires safety flags to persist across cycles unless
  an explicit, validated clearance resets them.
- Modules never initiate external effects; they expose outputs for callers that
  choose to act under separate privilege constraints.

## Diagrams

Sequence diagrams illustrating cycle flow, pulse resolution, and self-model
updates are located in `docs/diagrams/`.
