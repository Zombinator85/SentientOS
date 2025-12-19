## Affective Context Contract v1.0

SentientOS records affective context as continuous telemetry overlays. These
signals are descriptive only: they annotate perception and action artifacts but
never alter policy evaluation, permissions, or action selection.

### Requirements
- **Continuous**: every action, perception, and interaction must carry an
  affective overlay; cold or affect-blind paths are forbidden.
- **Bounded**: affective vectors are clamped to `[0, 1]` and include explicit
  bounds metadata.
- **Reason-coded**: every overlay declares a human-readable reason describing
  why the context was captured.
- **Decayable**: overlays declare `decay_seconds` and `timestamp` so consumers
  can treat affect as fading telemetry, not persistent state.
- **Overlay, not trigger**: affective context is attached alongside other
  signals and can be correlated with uncertainty or pressure, but it is never
  used as a reward, permission, or optimisation target.
- **No new emotions**: this contract reuses the existing emotion schema and
  does not introduce new affect labels.

### Integration expectations
- Components that act, decide, evaluate, explore, or ingest external content
  must expose hooks to attach affective overlays and register telemetry.
- Overlays must coexist with other signals without collapsing into them; policy
  fingerprints, decision gates, and execution order remain unaffected.
- External exploration (including internet/SCP reads) must continuously register
  affective context as gradients (fear, awe, curiosity, aversion) without
  implying avoidance, suppression, or belief.

### Backward compatibility
Existing emotion systems remain intact. Affective overlays wrap them in
bounded, decayable contexts and do not change schema or semantics.
