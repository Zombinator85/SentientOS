# Test-harness normalization note

This pass normalizes **test execution behavior**, not runtime architecture.

## Canonical entrypoint

Use:

```bash
python -m scripts.run_tests -q
```

`run_tests` remains the doctrine entrypoint and is responsible for:

- editable-install + dependency airlock checks
- deterministic pytest plugin bootstrap (`scripts.pytest_collection_reporter`)
- provenance + failure classification output in `glow/test_runs/`

## Direct `pytest` behavior

Direct pytest is not the primary path. It is guarded by `tests/conftest.py` and
expects the same editable-install contract. When needed for local debugging,
explicitly opt in with:

```bash
SENTIENTOS_ALLOW_NAKED_PYTEST=1 python -m pytest ...
```

## What was normalized

- Conftest optional-module stubs now avoid `yaml.__spec__ is None` /
  importlib-plugin instability by only stubbing when needed and setting
  deterministic module specs on stubs.
- `scripts.run_tests` now emits explicit environment/bootstrap failure
  classification when pytest exits without complete reporter payloads.
- Provenance now records `exit_reason=bootstrap-metrics-failed` for this class
  of harness failure so it is distinguishable from normal assertion failures.

## Remaining debt (separate follow-up)

- Large/legacy test selection policy in `tests/conftest.py` should be
  decomposed, but that is outside this normalization-only pass.
- Dual pytest config declarations (`pytest.ini` and `pyproject.toml`) should be
  reconciled in a dedicated configuration cleanup change.
