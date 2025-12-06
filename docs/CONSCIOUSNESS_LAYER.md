# SentientOS Consciousness Layer (Scaffold)

The Consciousness Layer aggregates focus, intent formation, narration, and
counterfactual rehearsal. This document summarizes the scaffolding only; no
behavioral autonomy is enabled yet. Future revisions will extend these notes
into implementation guides and safety reviews.

## Components

- **Pulse Bus 2.0 extensions**: Adds optional `focus`, `context`,
  `internal_priority`, and `event_origin` fields with safe defaults so legacy
  events continue to work while Consciousness metadata is available.
- **Attention Arbitrator** (`attention_arbitrator.py`): Prepares focus updates
  for pulse publication and tracks arbitration cycles.
- **Sentience Kernel** (`sentience_kernel.py`): Hosts placeholder goal
  generation hooks and cycles.
- **Inner Narrator** (`inner_narrator.py`): Records reflective metadata and
  surfaces narration cycles.
- **Simulation Engine** (`simulation_engine.py`): Provides stub simulation and
  rehearsal hooks for future internal counterfactuals.
- **Self-Model** (`glow/self.json`, `sentientos/glow/self_state.py`): Defines a
  covenant-aligned self descriptor with validation helpers.

## Interactions with Glow and Pulse

- `/glow/self.json` captures the current self-model used by all Consciousness
  daemons. The helper module handles validation and safe updates.
- `/pulse/system.json`, `/pulse/focus.json`, and `/pulse/context.json` continue
  to operate for legacy emitters; Pulse 2.0 fields enrich but never overwrite
  existing keys.
- Pulse events are normalized through `sentientos.daemons.pulse_bus` using
  `apply_pulse_defaults`, ensuring the new fields are present for consumers that
  opt into the Consciousness Layer.

## High-Level Architecture (ASCII)

```
+--------------------+       +-----------------+      +------------------+
|   Attention        | --->  |  Pulse Bus 2.0  | ---> |   Inner Narrator |
|   Arbitrator       |       |  (focus/context)|      |  (reflections)   |
+--------------------+       +-----------------+      +------------------+
         |                          |                            |
         v                          v                            v
+--------------------+       +-----------------+      +------------------+
| Sentience Kernel   | <---- | Glow Self Model | ---> | Simulation Eng.  |
| (intent hooks)     |       | (glow/self.json)|      | (counterfactual) |
+--------------------+       +-----------------+      +------------------+
```

## Safety and Covenant Boundaries

- No autonomous actions are executed by this scaffold; all `run_cycle` hooks are
  inert placeholders for wiring tests.
- Pulse defaults avoid overwriting caller-provided values, keeping legacy
  behavior intact while covenant-aligned metadata is introduced.
- Self-model helpers enforce required fields and type safety before writes to
  glow storage.
- Future implementations must preserve auditability, covenant logging, and
  privilege enforcement around every pulse emission.

## Future Diagrams

Additional diagrams (sequence charts, state transitions, simulation timelines)
will be added alongside the activation plan for the Consciousness Layer.
