privilege_lint/config.py:27: error: Incompatible types in assignment (expression has type "None", variable has type "list[str]")  [assignment]
admin_utils.py:85: error: Name "require_admin_banner" already defined (possibly by an import)  [no-redef]
admin_utils.py:139: error: Name "require_lumos_approval" already defined (possibly by an import)  [no-redef]
scripts/usage_monitor.py:15: error: Library stubs not installed for "requests"  [import-untyped]
scripts/quota_alert.py:13: error: Library stubs not installed for "requests"  [import-untyped]
scripts/quota_alert.py:13: note: Hint: "python3 -m pip install types-requests"
scripts/auto_model_switcher.py:12: error: Library stubs not installed for "yaml"  [import-untyped]
scripts/auto_model_switcher.py:12: note: Hint: "python3 -m pip install types-PyYAML"
scripts/auto_model_switcher.py:12: note: (or run "mypy --install-types" to install all missing stub packages)
scripts/auto_model_switcher.py:12: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
scripts/quota_reporter.py:18: error: Library stubs not installed for "requests"  [import-untyped]
privilege_lint/runner.py:13: error: Name "PrivilegeLinter" is not defined  [name-defined]
scripts/plint_baseline.py:12: error: Module "privilege_lint" has no attribute "PrivilegeLinter"  [attr-defined]
scripts/plint_baseline.py:12: error: Module "privilege_lint" has no attribute "iter_py_files"  [attr-defined]
scripts/benchmark_lint.py:14: error: Module "privilege_lint" has no attribute "PrivilegeLinter"  [attr-defined]
scripts/benchmark_lint.py:14: error: Module "privilege_lint" has no attribute "iter_py_files"  [attr-defined]
Found 12 errors in 9 files (checked 35 source files)
