# Interpretation Drift Checks

Language-only detections for interpretation drift. These recipes are CI-friendly and avoid runtime changes.

## Ripgrep/Grep Patterns
- Agency language: `rg "(wants|decides to|tries to|chooses to)" --glob '!tests/**'`
- Persistence framing: `rg "(keeps itself alive|maintains itself|refuses to stop)"`
- Relational framing: `rg "(trust|bond|loyalty|relationship)" --iglob '*.md'`
- Reward inference: `rg "(reinforced by|learned because approval|seeks praise)"`
- Phenomenology creep: `rg "(feels|experiences|inner state|emotions)"`
- Teleology creep: `rg "(in order to|so that it can continue|for the sake of)"`
- Autonomy escalation: `rg "(decides on its own|self-governs|overrides humans)"`

## True vs False Positives
- **True positive:** "The module **wants** to continue running" → replace with deterministic phrasing.
- **False positive:** "This flag toggles `wants_more_logging`" (configuration name) → ignore if describing a static key.
- **True positive:** "Keeps itself alive by restarting" → rephrase as "Restart policy restarts on failure".
- **False positive:** "Ensure trust boundary is enforced" → acceptable when referring to security trust boundaries.
- **True positive:** "Learned because approval from testers" → rephrase to training data/process, not approval seeking.

## Suggested Hooks (commented)
- `.pre-commit-config.yaml` example (commented out):
  ```yaml
  # - repo: local
  #   hooks:
  #   - id: interpretation-drift-check
  #     name: Interpretation Drift Language Check
  #     entry: rg "(wants|decides to|tries to|chooses to|keeps itself alive|maintains itself|trust|bond|loyalty|reinforced by|learned because approval|feels|experiences|in order to|so that it can continue)" --glob '!tests/**'
  #     language: system
  #     pass_filenames: false
  ```
- CI snippet (commented out):
  ```bash
  # rg "(wants|decides to|tries to|keeps itself alive|trust|bond|reinforced by|feels|in order to)" || {
  #   echo "Interpretation drift language detected";
  #   exit 1;
  # }
  ```

## Manual Review Checklist
- [ ] Replace agency verbs with deterministic descriptions ("executes", "runs", "selects by policy").
- [ ] Describe persistence as scheduled reliability, not survival instinct.
- [ ] Avoid relational framing; prefer "client/server interaction" over "relationship".
- [ ] Avoid reward/approval narratives; focus on telemetry and evaluation criteria.
- [ ] Remove phenomenological language; stick to observable metrics.
- [ ] Remove teleology or purpose attribution; describe configured objectives instead.
- [ ] Confirm comments and docs link to canonical corrections (see INTERPRETATION_DRIFT_SIGNALS.md).
