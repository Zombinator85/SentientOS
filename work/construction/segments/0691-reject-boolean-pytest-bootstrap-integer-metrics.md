# Sequence 691: reject boolean pytest bootstrap integer metrics

The pytest bootstrap verifier used `isinstance(value, int)` for collected-test and call-phase counts. A malformed provenance payload with `tests_collected: true` and `call_phase_outcome_count: true` was reported as `pytest_bootstrap_ready`. It now accepts only exact JSON integers; the regression injects those boolean metrics through the child-process boundary and requires a fail-closed status.

The tested code-only tree is `aa9d223d55a754e4cabd171384c36a4fb497ca42`, based on verified main `5bb87a776aec431f140d8d311458a62ca81cf5e2` / `2cdb7b74be24f98eb75e5d936bb777cee935e976`. The focused bootstrap suite passed 7/7, and targeted mypy reports no issues. Only `scripts/verify_pytest_bootstrap.py` and `tests/test_pytest_bootstrap_inertness.py` changed. Documentation is unaffected.
