# Contributing to SentientOS

SentientOS accepts contributions that preserve operator accountability,
auditability, and safe shutdown. For public terminology conventions, see the
[Public Language Bridge](docs/PUBLIC_LANGUAGE_BRIDGE.md).

## Contribution Contract (Engineering-First)

When you add or modify runtime code, preserve these repository invariants:

- Declare privilege requirements with the Privilege Access Procedure
  docstring.
- Keep authorization gates explicit and auditable.
- Route operational events through the logging helpers (no silent writes).
- Keep audit-chain validation green in local checks and CI.

All new scripts must start with the Privilege Access Procedure docstring,
followed by `require_admin_banner()` and `require_lumos_approval()`, before any
imports. These calls are enforced by `privilege_lint.py`.

```python
"""Privilege Access Procedure: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from sentientos.privilege import require_admin_banner, require_lumos_approval
```

Use `scripts/templates/cli_skeleton.py` as the starting point for any new
command-line interface. You can also run `python scripts/new_cli.py <name>` to
copy the skeleton automatically.

## Reviewer Checklist

- [ ] Docstring `"Privilege Access Procedure: Do not remove. See doctrine for details."` present at the top
- [ ] `require_admin_banner()` invoked before any other logic
- [ ] `require_lumos_approval()` called immediately after `require_admin_banner()`
- [ ] Logs created using `logging_config.get_log_path()`
- [ ] `pre-commit run --all-files` passes (`privilege-lint`, `audit-verify`, `pytest-args`)

Pull requests lacking these checks fail CI.

CI runs `pre-commit run --all-files` before the test suite, then executes
`python privilege_lint.py`. If any hook (`privilege-lint`, `audit-verify`, or
`pytest-args`) fails, the job fails.

Run `python privilege_lint.py` locally before submitting a pull request. You
can also link `./.githooks/pre-commit` into `.git/hooks` to run lint and audit
checks before each commit. The hook also runs
`python verify_audits.py logs/` to ensure audit logs remain valid.

First-time contributors can read
[FIRST_WOUND_ONBOARDING.md](docs/FIRST_WOUND_ONBOARDING.md) and submit the
**Share Your Contributor Story** issue when opening their pull request.

## Internal-language note

Internal doctrine may refer to privileged approval (internal codename:
blessing), operator procedure (legacy term: ritual), or governance
control plane (internal codename: cathedral). Public contributor guidance should
lead with the engineering terms above.

## Plugin & Extension Guidelines

External plug-ins and extensions interact with core audit logs. To contribute
one:

- Provide a `register` function using `plugin_framework.register_plugin`.
- Include a module-level docstring describing behavior and permissions.
- Use trust-engine logging helpers; avoid direct file writes.
- Document external dependencies in your pull request.

## Documentation & Types

Run `python scripts/build_docs.py` to build the documentation site. Ensure
`mypy --strict` runs without errors.

### MkDocs preview

Use `mkdocs serve` to preview docs locally.

### CI Workflow

Every pull request runs these checks:

```yaml
- name: Privilege lint
  run: python privilege_lint.py
- name: Run tests
  run: python -m scripts.run_tests
- name: Type check
  run: mypy --strict
- name: Verify audits
  run: LUMOS_AUTO_APPROVE=1 python verify_audits.py logs/
```

When running `verify_audits.py` manually, set `LUMOS_AUTO_APPROVE=1` or use
`--no-input` to bypass the Lumos privileged approval prompt.

### Test discovery & drift coverage

Pytest discovery is allowlisted via `pytest.ini` under `testpaths`. Drift tests
are listed there, so they run as part of the default suite. Default invocations
are quiet because `pytest.ini` sets `addopts = -q`.

Supported test commands:

- `python -m scripts.run_tests` (default suite; quiet due to `addopts = -q`)
- `python -m scripts.run_tests tests/test_drift_alerts_contract.py`
- `python -m scripts.run_tests tests/test_dashboard_drift_api.py`
