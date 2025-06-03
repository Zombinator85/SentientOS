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
