# Consciousness Layer Scaffold

This document captures the current scaffolding for the Consciousness Layer
modules, laying groundwork for arbitration, kernel intent generation, internal
narration, and simulation support. Future iterations should expand these notes
into a full specification and migration guide.

## Components

- **Attention Arbitrator** (`attention_arbitrator.py`): selects a focus event
  using priority-aware ordering with novelty, relevance, and reliability
  tie-breakers. Exposes helpers for focus and context snapshots.
- **Sentience Kernel** (`sentience_kernel.py`): generates autonomous proposals
  when the system is idle while filtering a small forbidden-goal list.
- **Inner Narrator** (`inner_narrator.py`): records reflective summaries with
  mood, confidence, and optional tags, and can persist to JSONL.
- **Simulation Engine** (`simulation_engine.py`): runs internal counterfactuals
  with deterministic confidence scaling based on participant count.

## Data Stores

- `/pulse/system.json` defines the upgraded pulse envelope with priority and
  interrupt metadata.
- `/pulse/focus.json` and `/pulse/context.json` hold arbitration outputs.
- `/glow/self.json` establishes the shared self-model schema.
- `/glow/introspection.jsonl` captures introspective entries.
- `/glow/simulations/` holds simulation artifacts.

## Sandbox and Safety

The Consciousness Layer remains disabled by default until runtime wiring and
safety policies are integrated. Covenant and integrity enforcement must wrap all
emissions before these modules are used in production.
