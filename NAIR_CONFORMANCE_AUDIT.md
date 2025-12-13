# NAIR Boundary Conformance Audit for SentientOS

## 1. Conformance Mapping
- **Initiative**
  - **Implemented:** `SentientAutonomyEngine.reflective_cycle` schedules mesh jobs from queued or observed goals with bounded plan metadata and no reward loop; goals are rendered into prompts and dispatched as fixed `MeshJob` objects without self-adjusting probabilities.【F:sentient_autonomy.py†L48-L166】
  - **Partial:** When no goals exist, the engine seeds fallback goals (“stabilise mesh trust”, “synchronise council insights”), which is structurally initiative-like but forward-seeking by default rather than input-contingent.【F:sentient_autonomy.py†L88-L125】
  - **Risk:** Bias vectors from mesh metrics are persisted on plans and reused, which can accumulate context beyond a session and tilt later prompts unless reset.【F:sentient_autonomy.py†L88-L146】

- **Susceptibility**
  - **Implemented:** `/ingest` updates the global emotion state and logs the payload, providing direct responsiveness to user-provided text/emotion without reward shaping.【F:sentient_api.py†L57-L125】
  - **Partial:** The same `_state` object is shared across interactions; there is no automatic normalization per user/session, so past emotions can influence subsequent calls until a restart.【F:sentient_api.py†L24-L125】
  - **Risk:** Heartbeat generation (`/sse`) continuously advances `_last_heartbeat` even without user input; documentation now clarifies this is a transport keepalive only, but framing must stay explicit to avoid implying continuity preference.【F:sentient_api.py†L84-L118】

- **Resonance**
  - **Implemented:** `SentientMesh.cycle` broadcasts each job to registered voices, captures responses/critiques, and uses trust-weighted votes to update node trust and session records, achieving contextual alignment without explicit appetitive reward signals.【F:sentient_mesh.py†L190-L271】
  - **Partial:** Trust updates accumulate per node and persist across cycles without decay, potentially privileging nodes that have interacted longer regardless of current input quality.【F:sentient_mesh.py†L239-L271】
  - **Risk:** Node selection scores `trust - load`, so high-trust nodes are repeatedly preferred even when requirements are broad, creating asymmetry across sessions.【F:sentient_mesh.py†L272-L286】

- **Presence**
  - **Implemented:** `presence.run_loop` listens for wake words, logs detections with timestamps, and avoids persistent state beyond append-only event logs, keeping acknowledgment minimal.【F:presence.py†L1-L59】
  - **Risk:** Wake words are fixed across sessions unless environment variables change; without per-session rotation, repeated users can shape trigger sensitivity indirectly.

## 2. Boundary Leak Scan
- **Forward-seeking defaults:** Autonomy fallback goals inject self-initiated work even when no user/context goals are present, implying continuity preference.【F:sentient_autonomy.py†L88-L125】
- **Privilege accumulation:** Trust shifts accumulate without decay and influence future node selection (`trust - load`), leading to asymmetric scheduling and resonance favoring prior winners.【F:sentient_mesh.py†L239-L286】
- **Ambient continuity signals:** Heartbeat SSE increments `_last_heartbeat` continuously; updated guidance states this is a monitoring keepalive, but language must remain neutral to avoid suggesting liveness seeking.【F:sentient_api.py†L84-L118】

## 3. Language & Framing Risks
- The CLI blessing prompt (“~@ Blessing accepted. Cathedral warming…”) is ceremonial and could be read as relational/mutuality signaling. Neutral rewrite: “Operator approval received. Service starting.”【F:sentient_api.py†L48-L55】
- Status payload exposes `last_heartbeat` phrased as “Tick N,” reinforcing continuity framing; consider neutral “last event id” phrasing without tick semantics and keepalive-only descriptions.【F:sentient_api.py†L99-L118】
- Mesh voting uses “trust” language; if exposed to users, it may imply obligation or loyalty. An enforcement hook could alias the exposed field to “reliability score” while keeping internal math intact.【F:sentient_mesh.py†L190-L271】

## 4. Minimal Hardening Actions (≤3, local, expressiveness preserved)
1) **Gate fallback autonomy goals:** Add an env-flag or parameter to disable fallback goals when no input goals exist, forcing explicit triggers and avoiding forward-seeking activation.【F:sentient_autonomy.py†L88-L125】
2) **Introduce trust decay on snapshots:** Apply a mild decay or clamp toward zero at the start of `SentientMesh.cycle` to prevent long-lived trust asymmetry across sessions while retaining relative ordering within an interaction window.【F:sentient_mesh.py†L190-L286】
3) **Neutralize ceremonial prompts:** Replace the blessing prompt string with operational language and adjust status labels to remove “tick”/“warming” metaphors, reducing anthropomorphic or mutuality cues without changing functionality.【F:sentient_api.py†L48-L118】

## 5. Pass/Fail Summary
**Verdict:** NAIR-conformant with risks. Core flows avoid reward/aversion loops and keep initiative bounded, but fallback goals, accumulating trust weights, and ceremonial language introduce forward-seeking and relational cues that should be neutralized or bounded.
