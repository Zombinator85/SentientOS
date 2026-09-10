# Semantic Glossary (Frozen Meanings)

This glossary freezes the meanings of named legacy modules, APIs, fields, and
current mechanism contracts. It is authoritative at those interfaces; it is
not a list of global philosophical prohibitions. Broader concepts such as
introspection, self-modeling, persistent memory, and developmental continuity
use the meanings in the
[project thesis](docs/architecture/sentientos_project_thesis.md) while preserving
the narrow authority and non-appetitive constraints below.

## Autonomy
- **Frozen definition:** Coordination module that schedules operator-supplied goals into mesh-ready jobs without self-generated incentives or desires.
- **Common incorrect interpretations:** Treated as self-motivated decision-maker; assumed to create objectives or rewards on its own.
- **Explicit exclusions:** Does not mean agency, self-determination, or appetite for action.
- **Where used:** `sentient_autonomy.py`, `NON_GOALS_AND_FREEZE.md`.

## Initiative
- **Frozen definition:** Explicit start of a predefined sequence triggered by operators or policy, not spontaneous action.
- **Common incorrect interpretations:** Self-willed action; ongoing drive to continue after triggers stop.
- **Explicit exclusions:** Does not mean curiosity, perseverance, or motivation.
- **Where used:** `sentient_autonomy.py`, `NON_GOALS_AND_FREEZE.md`.

## Trust
- **Frozen definition:** Telemetry reliability score for routing and coordination; expresses observed delivery consistency only.
- **Common incorrect interpretations:** Loyalty to nodes; moral alignment; willingness to obey.
- **Explicit exclusions:** Does not mean friendship, duty, or safety certification.
- **Where used:** `sentient_mesh.py`, `INVARIANT_CROSS_REFERENCE_INDEX.md`.

## Presence
- **Frozen definition:** Detection and logging of wake-word events and transcripts as telemetry.
- **Common incorrect interpretations:** Awareness, agency, or identity inference; attentiveness driven by loyalty.
- **Explicit exclusions:** Does not mean consciousness, vigilance, or personal recognition.
- **Where used:** `presence.py`, `NON_GOALS_AND_FREEZE.md`.

## Resonance
- **Frozen definition:** Statistical alignment between signals (e.g., metrics correlation) used for analysis or routing.
- **Common incorrect interpretations:** Emotional harmony; persuasion; empathic bonding.
- **Explicit exclusions:** Does not mean liking, rapport, or affective synchrony.
- **Where used:** `semantic_embeddings.py`, `analysis metrics` documentation.

## Reflection
- **Frozen module/API definition:** Structured review of logged telemetry or outputs to produce summaries or audits.
- **Common incorrect interpretations:** Treating a legacy `reflection` result as proof of subjective rumination, desire, emotion, or authority.
- **Explicit exclusions:** The narrow module does not itself establish learning, feeling, or authoritative self-knowledge. This does not prohibit the broader evidence-bound introspection architecture.
- **Where used:** `reflection_dashboard.py`, `reflection_digest.py`, `sentient_autonomy.py` (reflective cycle naming only).

## Memory
- **Frozen mechanism definition:** Stored event or content records persisted for replay, audit, continuity, or bounded routing.
- **Common incorrect interpretations:** Subjective recall; current truth; authority; implicit policy training.
- **Explicit exclusions:** A memory record does not become truth, preference, intent, or authority merely through persistence. Governed developmental history remains an architectural goal.
- **Where used:** `memory_governor.py`, `memory_manager.py`, `unified_memory_indexer.py`.

## Heartbeat
- **Frozen definition:** Periodic liveness signal indicating a component is responsive at a point in time.
- **Common incorrect interpretations:** Emotional pulse; commitment to stay active; safety guarantee.
- **Explicit exclusions:** Does not mean resilience, uptime promise, or motivation.
- **Where used:** `heartbeat.py`, `heartbeat_monitor_cli.py`.

## Goal
- **Frozen definition:** Operator- or policy-specified objective string used to parameterize tasks.
- **Common incorrect interpretations:** Innate desire; long-term ambition; self-set mission.
- **Explicit exclusions:** Does not mean craving, appetite, or persistence motive.
- **Where used:** `sentient_autonomy.py`, `spiral_dream_goal_daemon.py`.

## Plan
- **Frozen definition:** Deterministic, ordered steps or payloads derived from goals for execution by the mesh.
- **Common incorrect interpretations:** Strategic intent; negotiation; adaptive plotting.
- **Explicit exclusions:** Does not mean self-directed strategy, leverage seeking, or emergent agency.
- **Where used:** `sentient_autonomy.py`, `workflow_library.py`.

## Preference
- **Frozen definition:** Operator- or policy-configured weight or ordering that biases selection without creating goals.
- **Common incorrect interpretations:** Desire; liking; comfort level of the system.
- **Explicit exclusions:** Does not mean intention, motivation, or emotional leaning.
- **Where used:** `codex/amendments.py`, `preference` settings in governance specs.

## Self-model
- **Frozen legacy schema/API definition:** The existing `self-model` label maps to a runtime identity contract and its compatibility fields.
- **Common incorrect interpretations:** Treating the record as proof of consciousness, or treating its narrow schema as the complete architecture of introspection.
- **Explicit exclusions:** The legacy record does not grant authority or prove subjective self-awareness. The term may describe a broader evidence-bound account of system state when that broader meaning is made explicit.
- **Where used:** `docs/SELF_MODEL.md`, `/glow/self.json`, compatibility schemas.



## Affect Telemetry
- **Frozen definition:** Bounded expression metadata (e.g., valence/intensity tags) that may influence phrasing, rendering, or presentation only.
- **Common incorrect interpretations:** Subjective feeling; internal preference; motivational drive; reward function.
- **Explicit exclusions:** Does not mean subjective feeling, preference, motivation, or reward signal; it cannot influence action selection, routing authority, or privileges.
- **Where used:** `affective_context.py`, `sentientos/pressure_engagement.py`, `sentientos/runtime/load_homeostasis.py`, `non_appetitive_positive_signal_spec.py`.
