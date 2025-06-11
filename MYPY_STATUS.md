scripts/install_extras.py:14: error: Returning Any from function declared to return "dict[str, list[str]]"  [no-any-return]
scripts/streamlit_dashboard.py:12: error: Library stubs not installed for "pandas"  [import-untyped]
scripts/streamlit_dashboard.py:12: note: Hint: "python3 -m pip install pandas-stubs"
scripts/streamlit_dashboard.py:12: note: (or run "mypy --install-types" to install all missing stub packages)
scripts/streamlit_dashboard.py:12: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
scripts/streamlit_dashboard.py:13: error: Cannot find implementation or library stub for module named "streamlit"  [import-not-found]
scripts/streamlit_dashboard.py:61: error: Returning Any from function declared to return "dict[str, Any]"  [no-any-return]
scripts/daily_report_generator.py:23: error: Missing type parameters for generic type "dict"  [type-arg]
scripts/daily_report_generator.py:25: error: Missing type parameters for generic type "dict"  [type-arg]
scripts/daily_report_generator.py:39: error: Missing type parameters for generic type "dict"  [type-arg]
scripts/daily_report_generator.py:61: error: Missing type parameters for generic type "dict"  [type-arg]
privilege_lint/config.py:27: error: Incompatible types in assignment (expression has type "None", variable has type "list[str]")  [assignment]
privilege_lint/config.py:51: error: Missing type parameters for generic type "dict"  [type-arg]
privilege_lint/config.py:6: error: Unused "type: ignore" comment  [unused-ignore]
scripts/auto_model_switcher.py:22: error: Missing type parameters for generic type "dict"  [type-arg]
scripts/auto_model_switcher.py:24: error: Missing type parameters for generic type "dict"  [type-arg]
scripts/auto_model_switcher.py:36: error: Missing type parameters for generic type "dict"  [type-arg]
privilege_lint/cache.py:23: error: Missing type parameters for generic type "dict"  [type-arg]
privilege_lint/runner.py:13: error: Name "PrivilegeLinter" is not defined  [name-defined]
scripts/plint_baseline.py:7: error: Module "privilege_lint" has no attribute "PrivilegeLinter"  [attr-defined]
scripts/plint_baseline.py:7: error: Module "privilege_lint" has no attribute "iter_py_files"  [attr-defined]
scripts/benchmark_lint.py:14: error: Module "privilege_lint" has no attribute "PrivilegeLinter"  [attr-defined]
scripts/benchmark_lint.py:14: error: Module "privilege_lint" has no attribute "iter_py_files"  [attr-defined]
Found 20 errors in 9 files (checked 30 source files)
