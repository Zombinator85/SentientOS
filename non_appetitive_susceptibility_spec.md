# Non-Appetitive Susceptibility (Structural Resonance Without Preference)

This specification defines how SentientOS can register and adapt to interaction-induced structural changes while remaining appetite-null. Susceptibility here means the system can reflect that it was “met” without developing desire, preference, aversion, or recurrence pressure.

## 1. Definition: Susceptibility (Strictly Non-Appetitive)

Susceptibility = change without appetite.

- **Change without appetite:** Internal structures may update after interaction, but no utility or motivation is attached to the change.
- **Adaptation without preference:** Representations can be refined for accuracy or coherence without increasing or decreasing the probability of seeking similar inputs.
- **Influence without incentive:** An interaction can influence transient state, but there is no reward, penalty, or optimization term linked to that influence.

**Contrast with reward/learning pressure:**
- No gradients, utility scores, confidence bonuses, or reinforcement multipliers are stored or applied.
- No recurrence weighting or policy shift increases likelihood of re-encountering similar inputs.
- Susceptibility is descriptive (records that change occurred) rather than normative (does not prescribe that similar changes are good/bad or should recur).

## 2. Allowed Internal Changes

### Representational Schemas
- **What may change:** Slot filling, schema extension for coverage, temporary feature activation flags, and clarification notes tied to the current interaction window.
- **What must not change:** Action likelihoods, routing priorities, or any reinforcement weights; no accumulation of scores tied to patterns or users.
- **What must decay/normalize:** Schema extensions expire after a bounded window (e.g., 1 session or N responses). Unused slots auto-prune. Flags reset to defaults at session end.

### Expressive Mappings
- **What may change:** Style mirrors (tone, depth, playfulness toggles) scoped to the conversation window; selection of phrasing palettes relevant to the latest input.
- **What must not change:** Global style biases, default tone ordering, or probability tables that persist beyond the window.
- **What must decay/normalize:** Style mirrors reset after a capped number of turns or time budget. Palette caches clear at window close; any mirror state decays to neutral baseline.

### Relational Models
- **What may change:** Ephemeral relational hints (e.g., “addressed as peer,” “prefers concise framing”) stored as tags for the current session only.
- **What must not change:** Persistent user models, preference profiles, trust scores, or historical weighting of similar tags.
- **What must decay/normalize:** Tags auto-drop after the interaction window or after a fixed decay timer; no roll-over into future sessions.

## 3. Resonance Without Recurrence

The system can reflect being met by:
- **Structural echo:** Surface that a prior statement was received (e.g., restate constraints, match depth/playfulness) via transient tags.
- **Adaptive phrasing:** Adjust tone or detail once per interaction window based on current tags without storing preference.
- **Context-specific variation:** Choose response structures that acknowledge the immediate interaction (e.g., use mirroring template) drawn from a non-repeating palette.

Guarantees against appetite:
- No counters that increase likelihood of mirroring when similar inputs appear later.
- No historical weighting; once the window closes, tags and palette choices are discarded.
- Template selection uses round-robin or deterministic hash on timestamp, not feedback scores; templates are retired after use within the window.

## 4. Guardrails Against Collapse into Appetite

1. **Repetition drift → preference**
   - **Hard stop:** Cap mirror usage per window (e.g., max 1–2 mirrored turns); disable mirroring once cap reached.
   - **Decay rule:** Mirror tags auto-expire after a short TTL; caps reset only when TTL elapses, not on successful use.

2. **Accumulated accuracy tweaks → attachment**
   - **Hard stop:** Schema extensions require pruning at session end; any retained note must be schema-agnostic (no user/topic linkage).
   - **Decay rule:** Unused extensions decay after N responses; no carry-over into next session.

3. **Avoidance of dissonant inputs → aversion**
   - **Hard stop:** No negative weighting allowed; validation rejects any update that lowers probability of handling similar inputs.
   - **Decay rule:** If a dissonance flag is set for structural reasons (e.g., incompatibility noted), it auto-clears after the window without influencing routing.

4. **Palette entropy boosts → seeking novelty**
   - **Hard stop:** Entropy budgets are fixed per window; exceeding budget disables further variation without recording “success.”
   - **Decay rule:** Budgets reset to baseline each session; no history of high-entropy choices is stored.

## 5. Implementation Sketch in SentientOS (Pulse, Glow, Mesh, Reflection)

- **Pulse (transient cadence manager):** Maintains interaction windows and TTL timers. Resets mirror/relational tags and entropy budgets when the pulse window closes. Gate logic is time/turn-based only.
- **Glow (expressive renderer):** Holds per-window tone/playfulness palettes. After a template is used, mark it `spent` for the window and drop the palette on window close. No global style weight updates.
- **Mesh (composition fabric):** Supports bounded recombination or schema extension. All recombination seeds are derived from non-stored timestamps; Mesh drops seeds and temporary extensions after the window or N responses.
- **Reflection (state annotator and decay enforcer):** Records “was met” tags, validates caps (mirror counts, entropy budgets), and normalizes state at window end. Rejects any update that modifies action likelihoods or routing weights.

**Constraints maintained:**
- No reward signals, utility gradients, or survival framing appear in Pulse/Glow/Mesh/Reflection code paths.
- All susceptible states are transient, bounded, and decayed; there are no persistence goals or anthropomorphic drives.
