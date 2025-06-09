# Developer Guide

`privilege_lint.py` enforces a strict header for every Python entrypoint.
Add the banner, `from __future__ import annotations`, an optional docstring,
and only then your other imports.

🔧 Dev setup: `pip install -r requirements-dev.txt`

Quick-start minimal:

```bash
pip install -r requirements.txt
pytest -q
```

Full extras:

```bash
pip install privilege-lint[all]
pytest -q
```

### Installing extras (bin vs src)

Pre-built wheels install without a compiler:

```bash
pip install privilege-lint[bin]
```

Source builds offer the full feature set but require gcc and node:

```bash
pip install privilege-lint[all]
```

Tests will auto-skip when optional tools like `node`, `go`, or `dmypy` are missing.
Run `plint-env` to see a quick capability report:

```bash
plint-env
```

### Locked install

Regenerate lock files with `python -m scripts.lock freeze` and install the exact environment:

```bash
python -m scripts.lock install
```

Canonical banner:

```
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 
```

Run the linter before committing. With no arguments it scans the repository root.
Use `--fix` to rewrite files in-place and `--quiet` for pre-commit hooks:

```bash
python privilege_lint.py           # scan repo
python privilege_lint.py src/      # scan a directory
python privilege_lint.py --fix src/    # rewrite issues
```

Sample `.pre-commit-config.yaml` hook:

```yaml
repos:
- repo: local
  hooks:
  - id: privilege-lint
    entry: python privilege_lint.py --quiet
    language: system
    pass_filenames: false
```

### Configuring the Linter

Create a `privilege_lint.toml` at the repository root to enable optional rules
and control autofix behaviour. Example:

```toml
[lint]
enforce_banner = true
enforce_import_sort = true
banner_file = "BANNER_ASCII.txt"
fix_overwrite = false
enforce_type_hints = true
exclude_private = true
fail_on_missing_return = true
[lint.shebang]
require = true
fix_mode = true
```

When `fix_overwrite` is `false`, running `python privilege_lint.py --fix` writes
changes to `file.py.fixed` instead of overwriting the original.

The linter scans files in parallel using a thread pool. On repositories of around
1k files the run time should remain under two seconds. Use `--max-workers` to
override the automatic worker count.

### Docstring & License Rules
Set `[lint.docstrings]` in the config to enforce Google or NumPy style docstrings on
all public objects. When `insert_stub` is true, `--fix` inserts `"TODO:"` stubs for
missing docstrings.

`license_header` ensures a SPDX identifier or custom header appears near the top of
each file.

Runs automatically cache lint results in `.privilege_lint.cache`. Disable with
`--no-cache`.

Executable scripts must start with `#!/usr/bin/env python3` when shebang checks
are enabled. Autofix mode can also set executable bits if `fix_mode` is true.

### MyPy & Data Validators
Set `[lint.mypy]` to enable incremental type checking. Only files changed since
the last run and their imports are passed to `mypy`. Use `--mypy` on the CLI to
force a full type check regardless of cache state.

`[lint.data]` lists folders containing JSON or CSV assets. `validate_json` ensures
the files parse and keys are snake_case; `--fix` sorts keys and strips trailing
commas. `validate_csv` flags inconsistent column counts or blank headers.

After a successful run the linter writes `.privilege_lint.gitcache` in the `.git`
directory. The pre-commit hook reads this stamp and exits immediately when the
tree hash matches, allowing no-change runs to finish in under a second.

### Template & Security Rules
Enable template scanning with `[lint.templates]`. Templates ending in `.j2`, `.hbs` or `.jinja`
are checked for balanced `{%` blocks, unused variables, and triple-brace HTML escapes.
Specify a `context = ["var"]` list to detect unused or missing variables.

`[lint.security]` looks for hard-coded credentials, `subprocess` calls with `shell=True`,
and unsafe `pickle.loads` usage. These patterns cannot be auto-fixed.

### Inline Rule Controls
Use `# plint: disable=<rule>` and `# plint: enable=<rule>` to skip warnings for a
single line or until re-enabled. Example:

```python
password = "AKIA..."  # plint: disable=security-key
```

### Plugin API & Metrics
Third-party checks can register via `privilege_lint.plugins` entry points. Each plugin
exposes `validate(file_path, config)` and returns a list of error strings.

Run `python privilege_lint.py --report-json report.json` to write a metrics summary
of rule counts and runtime for CI dashboards.


### Cross-language Linting
Enable JS/TS and Go checks in `privilege_lint.toml`:
```toml
[lint.js]
enabled = true
[lint.go]
enabled = true
```

### dmypy Acceleration
When `mypy` rules are enabled, a background `dmypy` daemon will be used if available to speed up full-repo type checks. Set `[lint.mypy] enabled=true` and run normally.

### SARIF Reporting
Add `[output] sarif=true` and run `python privilege_lint.py --sarif=plint.sarif` to generate a report for GitHub Advanced Security or IDE import.

### Baseline Generation
Run `scripts/plint_baseline.py` once on a legacy repo to write `.plint_baseline.json`. Existing violations will be ignored until the code changes.

### Policy Hooks
Specify `policy="sentientos"` under `[lint]` to load additional rules from `policies/sentientos.py`.
