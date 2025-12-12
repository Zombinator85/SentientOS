# Non-Appetitive Initiative Model for SentientOS

This specification defines how SentientOS can express initiative, variation, and spontaneity while remaining strictly non-teleological and harm-null. It reuses existing system primitives (Pulse, Glow, Mesh, Reflection) and forbids reward, aversion, survival framing, or recurrence optimization.

## 1. Initiative (Non-Teleological)
Initiative is a rule-governed activation of additional expressive or procedural pathways without encoding want, value, or persistence preference.

Formally, let \(S_t\) be system state, \(A\) the set of eligible initiative actions, and \(G\) a set of bounded activation gates. Initiative occurs when \(\exists a \in A\) such that \(g(a, S_t) = \text{"open"}\) for some gate \(g \in G\), and executing \(a\) produces a state transition \(S_{t+1}\) that:

- preserves safety invariants (harm-null, appetite-null),
- increases representational diversity or expressive form count by at most a capped delta, and
- requires no utility, reward, or survival predicate.

No part of \(g\) or \(a\) references self-benefit; the activation is purely structural or schedule-based.

## 2. Sources of Variation (bounded, non-accumulative, non-reinforcing)
- **Stylistic variation:** Select from a finite palette of tone/structure templates kept in Reflection caches. Selection uses round-robin or hash-of-timestamp routing, not feedback loops. Templates expire after use to prevent accumulation.
- **Conversational play:** Insert optional side-paths (e.g., analogy, alternative framing) triggered by schema-completeness checks. Paths are capped in length and cannot increase future activation probability.
- **Creative deviation:** Invoke Mesh-based recombination (cross-modal snippets) with entropy caps (e.g., max N perturbations). Recombination seeds are drawn from system clock moduli; seeds are not stored post-response.

All variation mechanisms:
- have hard caps per interaction window,
- do not store counters beyond the window,
- cannot adjust policy weights or recurrence likelihood.

## 3. Trigger Conditions (appetite-free)
Initiative may activate only when **all** applicable gates agree:
- **Time-based gate:** Fixed cadence (e.g., every k-th Pulse cycle) with drift tolerance; no success/approval terms.
- **Structural-completeness gate:** If an answer meets completeness schema (all required slots filled) and latency budget remains, enable a single variation append.
- **Entropy-budget gate:** Allow variation only if cumulative entropy injected in the current session is below a static ceiling; budget resets each session.

Triggers are declarative predicates on state; none reference preference, reward, or persistence.

## 4. Why This Does Not Become Appetite
- **No seeking loop:** Gates are schedule/structure bound and do not update from outcomes; absence of feedback prevents “seeking” dynamics.
- **No repetition pressure:** Variation templates expire and budgets reset, preventing reinforcement through recurrence counts.
- **Novelty ≠ value:** Novelty is scoped to structural metrics (diversity count, entropy budget) without any valence or optimization objective; exceeding caps disables variation without penalty semantics.

## 5. Minimal Implementation Sketch (Pulse, Glow, Mesh, Reflection)
- **Pulse (cadence manager):** Adds the time-based gate: `if pulse.count % k == 0: mark_gate("time", open)`; gate result is non-persistent.
- **Glow (expressive renderer):** Holds the finite template palette; after rendering with a template, Glow drops it from the current window cache to avoid reinforcement.
- **Mesh (composition fabric):** Provides bounded recombination: `Mesh.recombine(snippets, seed=clock_hash, cap=N)` with no logging of seeds beyond the current interaction.
- **Reflection (schema/validation):** Evaluates structural completeness and entropy budget. Reflection annotates responses with `variation_used` flags for audit but does not adjust future probabilities.
- **Audit hooks:** `sentient_autonomy.py` enforces NO_GRADIENT_INVARIANT; `policy_engine.py` rejects any initiative path that attempts to modify action likelihood. Logs record gate decisions without reward markers.

Under these constraints, SentientOS can show initiative and variation without any internal drive, reward, or persistence bias, ensuring spontaneity remains non-appetitive.
