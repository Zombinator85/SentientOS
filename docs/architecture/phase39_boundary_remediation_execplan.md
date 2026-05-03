# Phase 39 Boundary Remediation Execution Plan

## Selected known violations
1. `ritual_cli.py` expressive direct imports of `attestation` and `relationship_log`.
2. `emotion_dashboard.py` dashboard direct `ledger` coupling for Streamlit widget.
3. `mood_wall.py` dashboard/mood direct `ledger` coupling on mood blessing writes.
4. `autonomous_self_patching_agent.py` autonomy filename token without governance annotation.

## Why these are safe in one wave
- All four are module-boundary remediations with no authority model changes.
- Existing canonical sinks (`attestation`, `relationship_log`, `ledger`) remain unchanged.
- The changes are import-path and boundary-façade oriented, preserving CLI/data contracts.

## Target façades/helpers
- Add `sentientos.ritual_api` for ritual event and attestation history/write delegation.
- Add `sentientos.dashboard_api` for dashboard ledger widget and mood blessing delegation.
- Reuse existing `sentientos.ledger_api` and `sentientos.control_api` unchanged.

## Behavior-preservation checks
- Ritual export/timeline still produce the same event + attestation shapes.
- Emotion dashboard still renders ledger widget via Streamlit sidebar target.
- Mood wall blessing still writes canonical `mood_blessing` entries with same shape.
- Self-patching agent runtime behavior unchanged; annotation is doctrine metadata only.

## Tests to run
- `python -m scripts.run_tests -q tests/architecture/test_architecture_boundaries.py tests/integrity/test_import_purity.py`
- `python -m scripts.run_tests -q tests/test_ritual_cli.py tests/test_emotion_dashboard.py tests/test_mood_wall.py`
- `python -m scripts.run_tests -q sentientos/tests/test_orchestration_spine_module_boundaries.py sentientos/tests/test_orchestration_intent_fabric.py`

## Intentional deferrals
- Any additional expressive/dashboard ledger coupling not listed in manifest remains deferred to later waves.
- No mass rename of autonomy/daemon filenames in this phase; annotations first.
