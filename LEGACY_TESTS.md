# Legacy Test Status

Previously certain tests were excluded from CI runs due to missing tooling or
deprecated modules. These issues have been resolved.

All tests previously listed in this document have been restored and no longer
require special handling.

Passing tests can be run with:

```bash
bash setup_env.sh
pytest -m "not env"
```

Contributions to repair or remove these legacy tests are welcome. Update this
file as modules are healed.

January 2026 update: audit log schema fixes allow several historical tests to
run without custom patches. Remaining legacy items will be migrated in upcoming
sprints.

February 2026 update: further review quarantined obsolete suites while
modernized ones have been re-enabled in CI. Legacy coverage now matches
current modules.

March 2026 update: additional outdated tests were archived and the
remaining functional suites were modernized and re-enabled. CI now runs
370 tests.
