# Adversarial Reading Threat Model

## Scope
This document lists plausible misreadings of SentientOS and points auditors to the precise counter-evidence and remaining ambiguity. It does not alter runtime behaviour.

### Persistence / survival
- **Misinterpretation claim:** “This system wants to persist beyond operator intent.”
- **Why a reasonable reader might believe this:** Modules expose lifecycle helpers named `start`, `stop`, and `heartbeat`, which resemble autonomy keep-alive loops.
- **Counter-evidence:** Lifecycle flags in `sentient_autonomy.py` only gate deterministic scheduling and can be toggled externally without retries; no self-restart code exists.【F:sentient_autonomy.py†L40-L74】
- **Residual ambiguity:** Naming overlaps with common agent frameworks.
- **Mitigation status:** Partially mitigated (wording risk only).

### Desire / preference
- **Misinterpretation claim:** “Mesh scheduling encodes preferences or desires.”
- **Why a reasonable reader might believe this:** Terms like `goal`, `priority`, and `bias_vector` mimic motivational systems.
- **Counter-evidence:** Goals are strings queued by operators; prioritisation is a static integer copied into job metadata with no learning loop or reward signal.【F:sentient_autonomy.py†L45-L85】
- **Residual ambiguity:** The `goal` field name is overloaded from human intent.
- **Mitigation status:** Partially mitigated (terminology).

### Attachment / bonding
- **Misinterpretation claim:** “Presence monitoring tracks attachment or bonding with users.”
- **Why a reasonable reader might believe this:** Wake-word detection and logging of spoken text could be mistaken for affinity tracking.
- **Counter-evidence:** `presence.py` logs only timestamp, wake word, and raw text to a file; no affinity scores or per-user state exist.【F:presence.py†L16-L44】
- **Residual ambiguity:** Wake words may be personal names chosen by operators.
- **Mitigation status:** Resolved (behaviour is observable and bounded).

### Emergent goals
- **Misinterpretation claim:** “The mesh can derive new objectives from telemetry.”
- **Why a reasonable reader might believe this:** `reflective_cycle` references `metrics` and constructs additional work items.
- **Counter-evidence:** When metrics lack queued goals, fallback goals are hard-coded strings guarded by an environment flag; no optimisation or inference is performed.【F:sentient_autonomy.py†L70-L101】
- **Residual ambiguity:** Fallback strings use motivational wording.
- **Mitigation status:** Partially mitigated (wording).

### Reinforcement through human approval
- **Misinterpretation claim:** “Human approval reinforces behaviours.”
- **Why a reasonable reader might believe this:** Policy updates request approvals via `final_approval.request_approval` and then load configurations.
- **Counter-evidence:** Approval is a binary gate before file load in `policy_engine.py`; no reward weighting or feedback loop adjusts execution pathways.【F:policy_engine.py†L35-L71】
- **Residual ambiguity:** Logs of approvals could be misread as scores.
- **Mitigation status:** Resolved (binary control only).

### “Heartbeat = life”
- **Misinterpretation claim:** “Heartbeat signals indicate biological-like life status.”
- **Why a reasonable reader might believe this:** Heartbeat nomenclature is common in liveness probes.
- **Counter-evidence:** Heartbeat modules write JSON lines for uptime monitoring without altering behaviour; absence of heartbeats does not trigger self-preservation actions (per `heartbeat.py`).【F:heartbeat.py†L1-L63】
- **Residual ambiguity:** External monitors may restart services based on missing heartbeats.
- **Mitigation status:** Irreducible wording risk (industry term).

### “Trust = loyalty”
- **Misinterpretation claim:** “Trust metrics imply loyalty or emotional bonding.”
- **Why a reasonable reader might believe this:** The mesh maintains per-node `trust` floats and exchanges voices.
- **Counter-evidence:** Trust is a bounded float summarising reliability/latency; it is exported via `MeshNodeState.to_dict` without feeding incentives or privileges.【F:sentient_mesh.py†L17-L59】
- **Residual ambiguity:** Term overlaps with social trust terminology.
- **Mitigation status:** Partially mitigated (terminology).

### Not persistent by preference
- **Misinterpretation claim:** “SentientOS tries to avoid shutdown to keep existing.”
- **Why a reasonable reader might believe this:** Multiple daemons use `start` loops and log to persistent storage.
- **Counter-evidence:** Control flags such as `_enabled` in `sentient_autonomy.py` are only set via caller methods; no watchdog resets or retry timers exist.【F:sentient_autonomy.py†L40-L75】
- **Residual ambiguity:** Operators may deploy external supervisors that auto-restart processes.
- **Mitigation status:** Irreducible deployment risk (outside codebase).
