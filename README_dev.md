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
```

When `fix_overwrite` is `false`, running `python privilege_lint.py --fix` writes
changes to `file.py.fixed` instead of overwriting the original.

