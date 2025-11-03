# SentientOS Autonomy Operations

This document describes the autonomy hardening controls introduced for the v1.1.0-alpha rehearsal cycle. The features are driven
through `config.yaml` and `SENTIENTOS_*` environment overrides. The defaults are deliberately conservative so every subsystem must
be opted into explicitly in production.

## Feature Flags and Environment Overrides

Each section below references the YAML path and the matching environment variable. Environment overrides always take precedence
over the configuration file.

### Memory Curator

- `memory.curator.enable` / `SENTIENTOS_MEMORY_CURATOR_ENABLE`
- `memory.curator.rollup_interval_s` / `SENTIENTOS_MEMORY_CURATOR_ROLLUP_INTERVAL_S`
- `memory.curator.max_capsule_len` / `SENTIENTOS_MEMORY_CURATOR_MAX_CAPSULE_LEN`
- `memory.curator.forgetting_curve.half_life_days` /
  `SENTIENTOS_MEMORY_CURATOR_FORGETTING_CURVE_HALF_LIFE_DAYS`
- `memory.curator.forgetting_curve.min_keep_score` /
  `SENTIENTOS_MEMORY_CURATOR_FORGETTING_CURVE_MIN_KEEP_SCORE`

### Reflexion & Critic

- `reflexion.enable` / `SENTIENTOS_REFLEXION_ENABLE`
- `reflexion.max_tokens` / `SENTIENTOS_REFLEXION_MAX_TOKENS`
- `reflexion.store_path` / `SENTIENTOS_REFLEXION_STORE_PATH`
- `critic.enable` / `SENTIENTOS_CRITIC_ENABLE`
- `critic.policy` / `SENTIENTOS_CRITIC_POLICY`
- `critic.factcheck.enable` / `SENTIENTOS_CRITIC_FACTCHECK_ENABLE`
- `critic.factcheck.timeout_s` / `SENTIENTOS_CRITIC_FACTCHECK_TIMEOUT_S`

### Council & Oracle

- `council.enable` / `SENTIENTOS_COUNCIL_ENABLE`
- `council.members` / `SENTIENTOS_COUNCIL_MEMBERS`
- `council.quorum` / `SENTIENTOS_COUNCIL_QUORUM`
- `council.tie_breaker` / `SENTIENTOS_COUNCIL_TIE_BREAKER`
- `oracle.enable` / `SENTIENTOS_ORACLE_ENABLE`
- `oracle.provider` / `SENTIENTOS_ORACLE_PROVIDER`
- `oracle.endpoint` / `SENTIENTOS_ORACLE_ENDPOINT`
- `oracle.timeout_s` / `SENTIENTOS_ORACLE_TIMEOUT_S`
- `oracle.budget_per_cycle` / `SENTIENTOS_ORACLE_BUDGET_PER_CYCLE`

### Goal Curator & HungryEyes

- `goals.curator.enable` / `SENTIENTOS_GOALS_CURATOR_ENABLE`
- `goals.curator.min_support_count` / `SENTIENTOS_GOALS_CURATOR_MIN_SUPPORT_COUNT`
- `goals.curator.min_days_between_auto_goals` /
  `SENTIENTOS_GOALS_CURATOR_MIN_DAYS_BETWEEN_AUTO_GOALS`
- `goals.curator.max_concurrent_auto_goals` /
  `SENTIENTOS_GOALS_CURATOR_MAX_CONCURRENT_AUTO_GOALS`
- `hungry_eyes.active_learning.enable` /
  `SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_ENABLE`
- `hungry_eyes.active_learning.retrain_every_n_events` /
  `SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_RETRAIN_EVERY_N_EVENTS`
- `hungry_eyes.active_learning.max_corpus_mb` /
  `SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_MAX_CORPUS_MB`
- `hungry_eyes.active_learning.seed` /
  `SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_SEED`

### Deterministic Seeding

Set `determinism.seed` or `SENTIENTOS_SEED` to guarantee reproducible rehearsals, tests, and daemons. All entrypoints call
`sentientos.determinism.seed_everything()` before launching subsystems.

## Operational Playbooks

### Running a Rehearsal

1. Enable the required feature flags in `config.yaml` or by exporting `SENTIENTOS_*` variables.
2. Run `make rehearse` locally or in CI. The command executes `scripts/rehearse.sh` which invokes `sosctl rehearse`.
3. Inspect `glow/rehearsal/latest/` for:
   - `REHEARSAL_REPORT.json` (signed)
   - `INTEGRITY_SUMMARY.json` (signed)
   - `metrics.snap`
   - `logs/runtime.jsonl`

If the oracle degrades during rehearsal the council records a deferred vote with quorum state and peer review evidence from the
critic.

### Emergency Oracle Fallback

When `/admin/status` shows the oracle in `degraded` mode:

1. Confirm the fallback message in the rehearsal or runtime logs.
2. Leave the council in deferred state until quorum can be re-established or the oracle returns to `online`.
3. Re-run `sosctl rehearse --cycles 1` after remedial work to ensure the circuit breaker resets to the online mode.

### Investigating Critic Disagreements

The critic increments `sos_critic_disagreements_total` and pushes peer review context to the quarantine log. Use
`sosctl reflexion run --since 1d` to capture narrative notes and `sosctl council vote --amendment <id>` to re-run the vote once the
peer review completes.
