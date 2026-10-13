# 0103 — Make targeted scorer modules type-clean without broadening the gate

Source baseline: `da44db5c4f847f32855115a81a37e9d27435b69f`, tree `4a28e970d9b28c0355113fb923164109e7c43148`.

The digest-only scorer change left three localized typing diagnostics in the two experiment modules: an `Any` return from the canonical digest wrapper and optional score-count arithmetic that was guarded at runtime but not narrowed for mypy. Added precise casts at those existing typed boundaries. No authority, scoring, or runtime behavior changed.

`mypy --follow-imports=skip sentientos/developmental_model_replacement_experiment.py sentientos/developmental_history_intervention_experiment.py` now reports **no issues in either changed module**. A focused scorer run covering no-replay treatments, digest-only score recovery, historical v1 compatibility, and preregistered suite transfer completed with five passing selected cases; the full 123-test developmental scorer/history/cognition suite passed immediately before this type-only adjustment. Both source files compile.

The ordinary import-following mypy invocation remains non-clean at 507 diagnostics across 87 repository files; this increment does not relabel those broader issues or claim a clean repository type check. No model/provider invocation or production verification occurred.

Commands:

- `python -m py_compile sentientos/developmental_model_replacement_experiment.py sentientos/developmental_history_intervention_experiment.py`
- `.venv/bin/python -m mypy --follow-imports=skip sentientos/developmental_model_replacement_experiment.py sentientos/developmental_history_intervention_experiment.py`
- `SENTIENTOS_GOVERNOR_ROOT=/tmp/sentientos-v5-suite-governor SENTIENTOS_FEDERATION_ROOT=/tmp/sentientos-v5-suite-federation SENTIENTOS_CONTROL_KERNEL_ROOT=/tmp/sentientos-v5-suite-kernel SENTIENTOS_RUNTIME_STATE_ROOT=/tmp/sentientos-v5-suite-runtime SENTIENTOS_REPO_ROOT=/workspace/work/sentientos-a54-exact .venv/bin/python -m pytest -q tests/test_developmental_objective_scoring.py -k 'probe_suite_scores_transfer_and_recovers_without_replay or new_digest_only_score_and_historical_output_retaining_score_are_readable or objective_treatments_and_no_replay' --tb=short`
