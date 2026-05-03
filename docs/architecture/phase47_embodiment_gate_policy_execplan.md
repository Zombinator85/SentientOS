# Phase 47 Embodiment Gate Policy ExecPlan

1. Current state: Phase45/46 gates exist in mic_bridge, feedback, screen_awareness, vision_tracker, multimodal_tracker with mode checks split across modules.
2. Skip causes: focused Phase45/46 tests were auto-classified as legacy tests and skipped by tests/conftest legacy policy (missing `no_legacy_skip`).
3. Unskip strategy: mark focused Phase45/46 and new Phase47 policy tests with `pytest.mark.no_legacy_skip`; keep hardware-free monkeypatch/temp-path approach.
4. Centralized policy design: introduce `sentientos/embodiment_gate_policy.py` with deterministic helpers (`normalize`, `resolve`, mode predicates, receipt fields) and shared mode constants.
5. Compatibility/default strategy: preserve compatibility_legacy default, allow explicit arg override first, then env var (`EMBODIMENT_INGRESS_GATE_MODE`), then module default fallback.
6. Modules updated: mic_bridge, feedback, screen_awareness, vision_tracker, multimodal_tracker, embodiment_ingress.
7. Tests: update Phase45/46 focused tests (non-skipped), add `tests/test_phase47_embodiment_gate_policy.py`, extend architecture checks for policy import/use and manifest mode visibility.
8. Deferred risks: compatibility_legacy still permits direct side effects/retention; kept visible in manifest as unresolved migration risk pending full adapter migration.
