admin_utils.py:81: error: Name "require_admin_banner" already defined (possibly by an import)  [no-redef]
admin_utils.py:135: error: Name "require_lumos_approval" already defined (possibly by an import)  [no-redef]
privilege_lint/config.py:27: error: Incompatible types in assignment (expression has type "None", variable has type "list[str]")  [assignment]
privilege_lint/runner.py:13: error: Name "PrivilegeLinter" is not defined  [name-defined]
scripts/plint_baseline.py:7: error: Module "privilege_lint" has no attribute "PrivilegeLinter"  [attr-defined]
scripts/plint_baseline.py:7: error: Module "privilege_lint" has no attribute "iter_py_files"  [attr-defined]
scripts/benchmark_lint.py:14: error: Module "privilege_lint" has no attribute "PrivilegeLinter"  [attr-defined]
scripts/benchmark_lint.py:14: error: Module "privilege_lint" has no attribute "iter_py_files"  [attr-defined]
Found 8 errors in 5 files (checked 35 source files)
