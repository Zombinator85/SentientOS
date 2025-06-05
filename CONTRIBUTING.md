# Contributing to SentientOS

All new scripts and entrypoints **must** invoke `admin_utils.require_admin_banner()` as the very first action. This banner enforces the Sanctuary Privilege Ritual and logs each attempt.
Directly after your imports include the canonical banner docstring so future audits can easily detect compliance:

```python
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
```

Add the following at the top of your script:

```python
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()  # Must immediately follow require_admin_banner()
```
## Reviewer Checklist

- [ ] Docstring `"Sanctuary Privilege Ritual: Do not remove. See doctrine for details."` present after imports
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
