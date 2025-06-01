# Contributing to SentientOS

All new scripts and entrypoints **must** invoke `admin_utils.require_admin_banner()` as the very first action. This banner enforces the Sanctuary Privilege Ritual and logs each attempt.
Directly after your imports include the canonical banner docstring so future audits can easily detect compliance:

```python
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
```

Add the following at the top of your script:

```python
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
```
## Reviewer Checklist

- [ ] Docstring `"Sanctuary Privilege Ritual: Do not remove. See doctrine for details."` present after imports
- [ ] `require_admin_banner()` invoked before any other logic

Pull requests lacking these will fail CI and be rejected.

Run `python privilege_lint.py` before submitting a pull request. You can also
link `./.githooks/pre-commit` into your `.git/hooks` folder to automatically
run the lint before each commit.
