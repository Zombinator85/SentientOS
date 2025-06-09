# Developer Guide

`privilege_lint.py` enforces a strict header for every Python entrypoint.
Add the banner, `from __future__ import annotations`, an optional docstring,
and only then your other imports.

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

Executable scripts must start with `#!/usr/bin/env python3` when shebang checks
are enabled. Autofix mode can also set executable bits if `fix_mode` is true.

