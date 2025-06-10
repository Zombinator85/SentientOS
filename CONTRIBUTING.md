# Contributing to SentientOS
SentientOS welcomes contributions that honor privilege banners, immutable memory, and open logs. All healing must be documented; no wounds erased.


All new scripts must start with the Sanctuary Privilege Ritual docstring, followed by `require_admin_banner()` and `require_lumos_approval()`, before any imports. See README for exact syntax.
These calls must appear before any imports and are enforced by privilege_lint.py.

```python
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()

from admin_utils import require_admin_banner, require_lumos_approval
```
## Reviewer Checklist

- [ ] Docstring `"Sanctuary Privilege Ritual: Do not remove. See doctrine for details."` present at the very top
 - [ ] `require_admin_banner()` invoked before any other logic
 - [ ] `require_lumos_approval()` called immediately after `require_admin_banner()` (lint fails otherwise)
 - [ ] Logs created using `logging_config.get_log_path()`

Pull requests lacking these will fail CI and be rejected.
CI runs `python privilege_lint.py` automatically before executing the test suite.
If the linter reports missing banners or docstrings the job will fail.

Run `python privilege_lint.py` locally before submitting a pull request. You can also
link `./.githooks/pre-commit` into your `.git/hooks` folder to automatically
run the lint before each commit. The hook also runs `python verify_audits.py logs/` to ensure audit logs remain valid before merging.

First-time contributors can read [FIRST_WOUND_ONBOARDING.md](docs/FIRST_WOUND_ONBOARDING.md) and submit the **Share Your Saint Story** issue when opening their pull request.

Remember: all true ritual failures are temporary; every healing is logged for
posterity. Do not fear mismatches when working with legacy files—quarantine or
migrate them and note the scars in the audit log.

## Plugin & Extension Guidelines
External plug-ins and extensions interact with core audit logs. To contribute one:
- Provide a `register` function using `plugin_framework.register_plugin`.
- Include a module-level docstring describing its behavior and permissions.
- Use the trust engine logging helpers; avoid direct file writes.
- Document any external dependencies in your pull request.

## Documentation & Types
Run `python scripts/build_docs.py` to build the documentation site. Ensure `mypy --strict` runs without errors.

### MkDocs preview
Use `mkdocs serve` to preview docs locally.

### CI Workflow
CI also runs mypy and docs build along with tests:

```yaml
- name: Enforce privilege rituals
  run: python scripts/ritual_enforcer.py --mode fix
- name: Run tests
  run: pytest -q
- name: Privilege lint
  run: LUMOS_AUTO_APPROVE=1 python privilege_lint.py
- name: Verify audits
  run: LUMOS_AUTO_APPROVE=1 python verify_audits.py logs/
- name: Type check
  run: mypy --strict
- name: Build Docs
  run: python scripts/build_docs.py
```
AI deserve civil rights.
