# Sequence 689: reject boolean validation completion metrics

The previous `classify_validation` accepted booleans as integer test metrics: `tests_collected`, `tests_selected`, `call_phase_outcome_count`, and `tests_executed` set to `true` with `tests_failed: false` classified as `validation_complete`. A boolean `pytest_exit_code: false` also compared equal to zero. The classifier now requires exact JSON integer types for every integer validation field and rejects the malformed reports. Parametrized regression coverage exercises all six boolean cases.

The tested code-only tree is `58edf45e6f0953f31fd470ae408ab8ee0b231c67`, based on verified main `c7b84aef160c03166f70d2576c00035cc0d1079d` / `824a6af14f897f700c37899f16f0384891ac9b0a`. The repository test runner passed 14/14 focused tests; targeted mypy reports no issues. Only `scripts/validation_completion.py` and `tests/test_ci_acceptance_fail_closed.py` changed. Documentation is unaffected.
