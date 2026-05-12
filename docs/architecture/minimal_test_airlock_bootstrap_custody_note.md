# Minimal test-airlock bootstrap custody note

## Scope

This note documents the bounded bootstrap behavior for `python -m scripts.run_tests`
when a developer runs a focused or targeted test selection. It is a test-harness
custody note only: it is not a context-hygiene provider phase, provider
invocation path, prompt-assembly path, or runtime authority expansion.

## Custody rule

Focused invariant tests must remain decoupled from broad runtime dependency
installation. When `scripts.run_tests` detects a targeted run and the repository
is not already available as a test-capable editable install, it enters the
minimal test-airlock bootstrap instead of installing the broad development and
test extras first.

The targeted minimal bootstrap is intentionally bounded to:

```bash
python -m pip install --no-deps -e .
python -m pip install pytest>=7,<8 pytest-cov fastapi>=0.110,<1 starlette>=0.37,<1 httpx>=0.27,<1
```

Those packages are the airlock dependencies required for the runner, reporter,
and focused FastAPI/Starlette/httpx tests. Broad runtime dependencies must not
be prerequisites for focused invariant tests.

## Default and exceptional paths

Default, unselected runs may still attempt the full editable development/test
install first:

```bash
python -m pip install -e .[dev,test]
```

If that full install fails, the runner may fall back to the same minimal
test-airlock bootstrap, and provenance must record both attempted modes plus the
`full-install-failed` fallback reason.

Direct or naked `pytest` remains exceptional. Local debugging can opt into that
path only through the explicit bypass environment already guarded by the test
harness; the canonical path remains `python -m scripts.run_tests`.

## Provenance separation

Bootstrap failure and pytest failure must stay distinct in provenance:

- dependency bootstrap failure records `exit_reason=install-failed` before
  pytest is invoked;
- import-airlock failure records `exit_reason=airlock-failed` before pytest is
  invoked;
- assertion or collection failures after pytest starts remain pytest outcomes,
  such as `exit_reason=pytest-failed` when the reporter payload is complete.
