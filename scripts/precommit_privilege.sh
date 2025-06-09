#!/usr/bin/env bash
set -e
STAMP_FILE=".git/.privilege_lint.gitcache"
TREE=$(git rev-parse HEAD^{tree})
if [[ -f "$STAMP_FILE" && $(cat "$STAMP_FILE") == "$TREE" ]]; then
    echo "privilege lint cache hit"
    exit 0
fi
if command -v pip-compile >/dev/null; then
    python scripts/gen_lock.py --check || { echo "Run make lock-refresh"; exit 1; }
fi
CFG_HASH=$(python - <<'PY'
from privilege_lint.config import load_config
from privilege_lint.cache import _cfg_hash
print(_cfg_hash(load_config()))
PY
)
NEWSTAMP="$TREE"
LUMOS_AUTO_APPROVE=1 python privilege_lint.py --quiet && echo "$NEWSTAMP" > "$STAMP_FILE"

