# Autonomous maintenance implementation backends

The durable watchdog configuration requires `implementation_backend` to be exactly
`local_codex` or `commissioned_local`. `local_codex` means a locally governed Codex
process and can use remote model inference. `commissioned_local` means the existing
SentientOS-commissioned local-model implementation worker. Neither backend is a
fallback for the other.

For `commissioned_local`, set `commissioned_local_activation` to the absolute path of
the operator-selected production activation produced by
`local_model_production_commissioning.activate`, and bind its exact bytes in
`commissioned_local_activation_digest`. The watchdog reloads this durable binding,
rejects a missing, malformed, substituted, stale, non-production, fallback, or
authority-map-mismatched activation, and reconstructs only its exact identity. For
`local_codex`, both activation fields must be null.

Backend construction failures, runtime/readiness failures, inference failures,
timeouts, malformed actions, exhausted budgets, denied tools, cancellation, lease
failure, and exhausted correction block or fail the selected worker; they never
change backend. Status and tick evidence identify the configured and instantiated
backend. Commissioned-local result and session evidence includes model identity,
lease/worktree identity, iteration and validation-feedback counts, lifecycle state,
and explicit zero remote/Codex/validation/commit/publication effects.

Both workers can only implement in the exact-base detached worktree under the
existing lease. Candidate selection, admission, deterministic validation,
corrective-continuation admission, commit, and publication remain owned by the
existing deterministic maintenance components. Model completion is not acceptance.

A real GGUF proof requires an existing production activation; it is never fabricated
or replaced by Codex. Run:

```bash
SENTIENTOS_COMMISSIONED_LOCAL_ACTIVATION=/absolute/path/to/activation.json \
python -m scripts.run_tests -q \
tests/test_maintenance_commissioned_local_agent.py::test_real_commissioned_local_model_integration_requires_explicit_fixture
```

That opt-in node proves real governed inference availability. The watchdog selector
and no-fallback path are covered separately by
`tests/test_maintenance_watchdog_backend_selection.py`.
