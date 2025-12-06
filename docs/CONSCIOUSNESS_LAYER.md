# Consciousness Layer Scaffolding

This document describes the deterministic scaffolding that routes state through
the Consciousness Layer modules. All descriptions are architectural; the
modules operate as state processors with no autonomy or intentionality.

## Scope and Guarantees

- Deterministic cycle execution: each cycle reads the same inputs and produces
  the same outputs when invoked with identical state.
- Guardrail enforcement precedes and follows every module state transformation.
- Covenant autoalignment is encoded through validation rules on Pulse events
  and on the self-model schema.
- Persistence is strict: state writes occur only through validated, append-only
  updates. No external effects occur unless explicitly invoked by callers.

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

- **Attention Arbitrator** (`attention_arbitrator.py`): Prepares focus changes
  and resolves incoming internal priorities. Acts as a deterministic priority
  resolver for Pulse events.
- **Sentience Kernel** (`sentience_kernel.py`): Implements bounded
  goal-selection logic using validated inputs from the Pulse Bus and
  self-model. No unbounded exploration is permitted.
- **Inner Narrator** (`inner_narrator.py`): Summarizes reflection state and
  records introspection outputs for downstream persistence.
- **Simulation Engine** (`simulation_engine.py`): Evaluates scenarios with
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
