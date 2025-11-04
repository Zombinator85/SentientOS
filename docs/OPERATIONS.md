# SentientOS Autonomy Operations

This document describes the autonomy hardening controls introduced for the v1.1.0-beta rehearsal cycle. The features are driven
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

### Budget Clamps

- `budgets.reflexion.max_per_hour` / `SENTIENTOS_BUDGET_REFLEXION_MAX_PER_HOUR`
- `budgets.oracle.max_requests_per_day` / `SENTIENTOS_BUDGET_ORACLE_MAX_REQUESTS_PER_DAY`
- `budgets.goals.max_autocreated_per_day` / `SENTIENTOS_BUDGET_GOALS_MAX_AUTOCREATED_PER_DAY`

Budget exhaustion changes the module status to `limited` in `/admin/status` and increments the corresponding
`sos_*_rate_limited_total` counters in `/admin/metrics`. Refill windows are one hour for reflexion and one day for oracle and goal
curators.

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

### Embodied Presence

- `audio.enable` / `SENTIENTOS_AUDIO_ENABLE`
- `audio.max_minutes_per_hour`
- `tts.enable` / `SENTIENTOS_TTS_ENABLE`
- `screen.enable` / `SENTIENTOS_SCREEN_ENABLE`
- `gui.enable` / `SENTIENTOS_GUI_ENABLE`
- `social.enable` / `SENTIENTOS_SOCIAL_ENABLE`
- `social.require_quorum_for_social_post`
- `conversation.enable` / `SENTIENTOS_CONVERSATION_ENABLE`
- `policy.autonomy_level` / `SENTIENTOS_POLICY_AUTONOMY`

When enabled, `/admin/status` includes `ears`, `voice`, `screen`, `gui`, `social`, and
`conversation` modules. Each entry reports backend health and remaining budgets.
`/admin/metrics` exports counters such as `sos_asr_segments_total`,
`sos_screen_captures_total`, and `sos_web_actions_total{kind=...}` to simplify live
monitoring. Quiet hours defined by `conversation.quiet_hours` suppress proactive
prompts and are mirrored in the status payload.

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

### Service Level Objectives

SentientOS v1.1.0-rc promotes a baseline set of SLOs encoded in `config.slos.yaml`. They are exposed in `/admin/status` and `/admin/metrics` with gauges prefixed `sentientos_slo*`.

| SLO | Target | Measurement |
| --- | --- | --- |
| `admin_api_availability` | ≥ 99.9% | ratio derived from `sos_admin_requests_total` and `_failures_total` |
| `rehearsal_success_ratio` | ≥ 0.98 | rehearsal cycles without degraded council/oracle |
| `council_quorum_latency_p95` | ≤ 2s | p95 of `sos_council_vote_latency_ms` histogram |
| `critic_disagreement_rate` | ≤ 5% | disagreements / council votes |
| `hungry_eyes_retrain_freshness` | ≤ 7 days | age of the last Hungry Eyes retrain |

Update the YAML file or override the targets in `/sentientos_data/config.slos.yaml` to customise the thresholds. The JSON payload returned by `/admin/status` now includes `slos`, `degraded_modules`, and `slo_breaches` to make incident triage explicit.

### Alert Snapshots

Run `./scripts/alerts_snapshot.sh` to materialise the current alert state under `glow/alerts/*.prom`. The rules ship under `ops/alerts/` and cover the following failure modes:

- `HighReflexionTimeouts` – reflexion latency max above budget.
- `NoQuorum` – council quorum misses observed.
- `OracleDegradedSustained` – oracle degraded for 15+ minutes.
- `CuratorBacklogHigh` – memory curator backlog over the configured ceiling.
- `HungryEyesStaleModel` – Hungry Eyes has not retrained within seven days.
- `EventSignatureMismatches` – rejected signed pulse events.

The script prints a JSON snapshot, emits firing gauges to stdout, and writes individual `*.prom` files to `glow/alerts/`.

### Privacy and Redaction

Logging now flows through a redaction middleware that hides e-mail addresses, bearer tokens, and 64+ character secrets by default. Tune behaviour in `config.yaml` under `privacy.redactions` to add whitelist entries or extra patterns. When `privacy.hash_pii` is enabled the memory curator hashes detected PII inside capsules and stores a reversible vault in `vow/keys/pii_vault.jsonl` for audit retrieval.

### Secrets Hygiene

`make audit` calls `scripts/scan_secrets.sh` which scans the staged files with ripgrep heuristics for bearer tokens, emails, and long lived secrets. Invoke the script manually before committing to catch stray credentials early.

### Performance Smoke Tests

`make perf` runs `scripts/perf_smoke.sh`, generates synthetic critic/reflexion/council decisions across `low|std|high` load profiles, and writes p50/p95 latency reports to `glow/perf/latest/summary.json`. Use the results as the baseline before kicking off a longer soak.
