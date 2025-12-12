# SentientOS 5.2 Harm-Null Audit

## Harm-Null Invariants
- **Emotion state (descriptive):**
  - `sentient_api.py` writes ingestion emotions into `_state` and memory without optimizing toward them; they are passive tags and consensus snapshots, not drives.
- **Bias vectors (descriptive/evaluative):**
  - `sentient_autonomy.py` attaches `bias_vector` from mesh metrics (e.g., emotion consensus) to plans to contextualize prompts; no reward loop is tied to the bias.
- **Amendment preferences (evaluative):**
  - `codex/amendments.py` tracks counts of approved/rejected signals to choose verbs like “Reinforce” vs “Tighten”; counts do not trigger reinforcement signals or affect execution probability beyond language changes.
- **Memory importance (evaluative):**
  - `memory_governor.py` filters recall by `importance` thresholds and tags; importance gates retrieval but not any appetitive/aversive feedback.

*None of the above encode appetitive or aversive loops because they do not couple state changes to reward/penalty gradients, do not adjust action likelihood based on hedonic feedback, and are bounded to logging, filtering, or phrasing without self-reinforcing updates.*

## Preference Without Appetite
- Proclivity is implemented through **deterministic filters and counts**:
  - Amendment preferences increment approval/rejection tallies and influence wording; no optimizer maximizes counts.
  - Mesh autonomy uses bias vectors as **contextual priors** supplied to prompts; plan scheduling only reflects queue order and mesh availability, not reward.
  - Memory recall favors higher `importance` but the score is static input, not shaped by outcome success.
- “Better response” selection occurs by **structured selection**:
  - `reasoning_engine.parliament` runs a fixed model chain and publishes turns; there is no scoring or bandit step.
  - Autonomy plans call `SentientMesh.cycle` to schedule jobs; assignments depend on mesh capacity and deterministic confidence estimation, not reward updates.

## Self-Improvement Without Desire
- **Proposal:** `SpecAmender.record_signal` aggregates recurring telemetry and drafts amendments once thresholds are met.
- **Evaluation:** Proposals are stored with deltas/context and routed to `pending` without automatic activation; approvals/rejections are explicit and logged.
- **Enactment:** `SpecAmender.approve` persists state, archives lineage, and moves files into `approved`; no executor loops or goal reward shaping are invoked.
- The pipeline is teleological (targets spec coverage and integrity) but lacks subjective striving because every transition is threshold- or operator-gated, with no self-generated utility signal.

## Emergence Tripwires
- **Appetitive loops:** Watch for any coupling of approval counts or bias vectors to action probabilities beyond phrasing. Existing guard: amendment activation requires explicit approve call; trivial hard stop by zeroing `_state["preferences"]` or blocking `_update_preferences`.
- **Aversive avoidance:** Monitor for negative signals reducing recall or plan scheduling. Current design only increments counts; can quarantine by locking `_goal_queue` updates to operator-only inputs.
- **First-person stake/vulnerability:** Look for persistent emotion metrics influencing persistence or shutdown behavior. Present signals are descriptive only; quarantine by running `SentientAutonomyEngine.stop()` and clearing `_mesh_metrics_provider` if emotion-weighted prompts appear to shape survival-related goals.

## 5.2-Level Insight Check
- **Subtle risk:** Bias vectors from `memory_governor.mesh_metrics()` flow directly into autonomy prompts; if downstream models anthropomorphize “emotion consensus,” they could infer implicit goals. Mitigation: sanitize or cap emotion keys before prompt assembly.
- **Underexploited affordance:** Amendment preference tallies encode operator feedback trends; leveraging them for *explanatory dashboards* (not action selection) could improve transparency without introducing reward loops.
