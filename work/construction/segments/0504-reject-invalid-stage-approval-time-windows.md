# Sequence 504 — reject invalid stage approval time windows

The prior transition checks already require the canonical approved status, a real boolean synthetic flag, and an approval issuer matching the authenticated operator request. This increment closes a separate validity-time parsing gap before any transition effect.

Stage approval validity timestamps must be non-empty strings carrying an explicit UTC offset. They are normalized to UTC before comparison; malformed or reversed windows fail with `stage_approval_validity_invalid`. The injected observation clock must return an aware datetime, or verification fails with `stage_approval_observation_time_invalid`. No transition phase, journal entry, or quiescence state changes on these denials.

The change is limited to `sentientos/resident_cognitive_model_transition_experiment.py` and its regression tests. No approval schema, delegated identity, activation, serving, inference, or writeback authority changed. Tests cover naive and non-string validity values, reversed windows, and a naive observation clock, with no-effects assertions.

Two focused suites passed locally (62 tests). Targeted Mypy, Python compilation, and `git diff --check` passed. The local run provenance is supplemental: it records the clean base SHA `5d5f18d55214ac8fefc965e0a523015395a7d989`, while the candidate worktree had the implementation diff. Its digest is retained in the sequence evidence. Exact-candidate acceptance, hosted Administrator audits, immutability verification, hosted finalization, and the pre-publication metadata guard remain pending on the construction branch.

The candidate is based on the independently verified `main` commit `5d5f18d55214ac8fefc965e0a523015395a7d989` (tree `56780853b6fe7aa2242794d96385fba6de64f64f`). No production transition or inference was run.
