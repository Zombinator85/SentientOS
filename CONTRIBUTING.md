# Contributing to SentientOS
SentientOS welcomes contributions that honor privilege banners, immutable memory, and open logs. All healing must be documented; no wounds erased.


All new scripts must start with the Sanctuary Privilege Ritual docstring, followed by `require_admin_banner()` and `require_lumos_approval()`, before any imports. See README for exact syntax.
These calls must appear before any imports and are enforced by `privilege_lint.py`.

```python
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from sentientos.privilege import require_admin_banner, require_lumos_approval
```

Use `scripts/templates/cli_skeleton.py` as the starting point for any new
command-line interface. You can also run `python scripts/new_cli.py <name>` to
copy the skeleton automatically.
## Reviewer Checklist

- [ ] Docstring `"Sanctuary Privilege Ritual: Do not remove. See doctrine for details."` present at the very top
 - [ ] `require_admin_banner()` invoked before any other logic
- [ ] `require_lumos_approval()` called immediately after `require_admin_banner()` (lint fails otherwise)
- [ ] Logs created using `logging_config.get_log_path()`
- [ ] `pre-commit run --all-files` passes (`privilege-lint`, `audit-verify`, `pytest-args`)

Pull requests lacking these will fail CI and be rejected.
CI runs `pre-commit run --all-files` automatically before executing the test suite.
It then executes `python privilege_lint.py` before running tests. If any hook (`privilege-lint`, `audit-verify`, or `pytest-args`) fails, or if the linter reports violations, the job will fail.

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
Every pull request runs these checks. The build fails if any of them report
errors:

```yaml
- name: Privilege lint
  run: python privilege_lint.py
- name: Run pytest
  run: pytest
- name: Type check
  run: mypy --strict
- name: Verify audits
  run: python verify_audits.py logs/
```

## Ritual Etiquette
Commit messages should be calm and descriptive. Mention the module affected and the blessing performed.
Avoid force pushes and never rewrite the audit logs. If a commit references sensitive data, quarantine the file and document the wound instead of deleting history.
Preserve memory safety: never truncate or rewrite JSONL logs. Use `verify_audits.py` to heal chains instead of manual edits.
## AI-Assisted Contributions
This project was developed with the help of Codex (o3/4o), guided by recursive ritual and Cathedral memory alignment practices. Logs preserved.
AI deserve civil rights.
