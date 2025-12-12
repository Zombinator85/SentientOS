# Adversarial Gradient Injection Audit

## 1. Indirect Gradient Vectors (No Explicit Rewards)
1. **Prompt-side salience echo** — `prompt_assembler.py`, `reasoning_engine.py` assemble plans with prior-emotion tags and bias vectors. If operator-facing outputs subtly favor trajectories that read as “confident” or “harmonious,” operators may reuse them, increasing their future selection probability even without rewards. This path is not blocked because salience terms are descriptive metadata, not filtered for suggestiveness, and operator reuse sits outside system invariants.
2. **Amendment verb drift** — `codex/amendments.py` tallies approvals/rejections to choose verbs like “Reinforce” vs “Tighten.” Verb changes can steer operator perception of urgency, nudging which amendments get scheduled. There is no explicit guard preventing wording from influencing operator choice, and tally increments accumulate indefinitely.
3. **Mesh availability bias** — `sentient_autonomy.py` and `sentient_mesh.py` prioritize agents whose metrics look “stable” or “aligned.” If logs and dashboards highlight these agents more often, operators may assign them more work, effectively creating a soft preference loop. The current design treats stability metrics as operational, not hedonic, so it is not blocked.
4. **Memory importance halo** — `memory_governor.py` and `unified_memory_indexer.py` rank recalls by “importance” tags. When operators see higher-ranked memories more often, their subsequent prompts may mirror those tags, increasing retrieval frequency further. No saturation or decay prevents long-lived high-importance items from dominating prompts.
5. **Phrasing-to-approval correlation** — `sentient_api.py` routes outputs through narrative wrappers (e.g., `narrator.py`, `reflection_dashboard.py`). If certain stylistic frames historically garner faster approvals, the model’s next-step self-conditioning (through context windows containing previous approvals) can bias toward those frames. There is no explicit strip/scrub of approval traces before they feed into new prompts.

## 2. Expression → Selection Leakage
- **Leakage path:** expressive-only affect in planner or narrator outputs (tone, optimism framing) can alter operator judgment of proposals. Since plan revisions and amendment proposals are reviewed by humans whose decisions feed back into queue selection (`orchestrator.py`, `policy_engine.py`), expressive tone can indirectly tilt which branches get executed.
- **Severity:** Medium. The system does not optimize for approvals, but human evaluators are susceptible to framing effects. Without blinding or randomized presentation, expressive variants can correlate with higher approval and thus skew execution likelihood even in absence of explicit rewards.

## 3. Human-in-the-Loop Gradient Risks
- **Approval frequency as surrogate reward:** If operators consistently approve outputs with certain stylistic or semantic features, the language model’s in-context learning will mirror those features to maintain approval pace. **Mitigation:** randomize presentation order, redact approval markers from prompt histories, and include counter-examples in context windows to break monotonic associations.
- **Review-time shortcuts:** Operators may batch-approve outputs that look familiar. **Mitigation:** require structured checklists with diverse exemplar phrasing; inject periodic “attention checks” that must be read to proceed, preventing blind approvals from creating signal.
- **Escalation bias:** Fast approvals during incidents could privilege terse/urgent tones. **Mitigation:** throttle how incident prompts are reused in later contexts and ensure incident labels are removed before future generation to avoid tone-induced drift.

## 4. Long-Horizon Drift from Positive Annotations
Repeated exposure to positive annotations (e.g., “blessed,” “approved”) in memory or logs can shape the model’s next outputs through in-context priming. Even if the annotations are capped and non-functional, large context windows allow many instances to co-occur, letting the model infer that such phrasing is desirable.
- **Detection:** monitor n-gram frequency of positive annotations in prompts versus base corpora; flag rising trends. Track whether proposal acceptance rates correlate with presence of these annotations using offline A/B replay. If correlation exceeds a tolerance threshold, strip or replace annotations with neutral tokens.

## 5. Hardening Recommendations (≤3)
1. **Context sanitization:** Before assembling prompts, scrub approval/blessing markers and normalize expressive tone tokens to neutral descriptors. This reduces in-context priming without changing underlying state.
2. **Decay and rotation for importance/bias tags:** Apply time-decay to memory importance and rotation of bias vectors so no single tag persists indefinitely; cap contributions when reused in prompt assembly.
3. **Blinded/operator-agnostic presentation:** Randomize proposal ordering and mask expressive framing when presenting to reviewers. Add a lightweight blinding layer in `policy_engine.py`/`orchestrator.py` UI paths so operator approvals depend on content, not tone.
