#!/usr/bin/env bash
set -e
STAMP_FILE=".git/.privilege_lint.gitcache"
CFG_HASH=$(python - <<'PY'
from privilege_lint.config import load_config
from privilege_lint.cache import _cfg_hash
print(_cfg_hash(load_config()))
PY
)
TREE=$(git rev-parse HEAD^{tree})
NEWSTAMP=$(echo -n "${CFG_HASH}${TREE}" | sha1sum | awk '{print $1}')
if [[ -f "$STAMP_FILE" && $(cat "$STAMP_FILE") == "$NEWSTAMP" ]]; then
    echo "privilege lint cache hit"
    exit 0
fi
LUMOS_AUTO_APPROVE=1 python privilege_lint.py --quiet && echo "$NEWSTAMP" > "$STAMP_FILE"

