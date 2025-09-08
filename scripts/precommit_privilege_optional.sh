#!/usr/bin/env bash
# Run privilege lint only if pyesprima is available
if python - <<'PY' >/dev/null 2>&1
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("pyesprima") else 1)
PY
then
    LUMOS_AUTO_APPROVE=1 scripts/precommit_privilege.sh
else
    echo "Skipping privilege lint: pyesprima not installed"
fi

