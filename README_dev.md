# Development Lint Modes

Pre-commit hooks run the privilege and audit linters in a warning mode so legacy
logs don't block everyday work. Failures are shown in yellow but the commit will
continue. To enforce strict linting you can pass `--strict` or set the
environment variable `SENTIENTOS_LINT_STRICT=1`.

Example:

```bash
export SENTIENTOS_LINT_STRICT=1
python privilege_lint.py --no-emoji
python verify_audits.py logs/ --no-emoji
```
