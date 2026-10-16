#!/usr/bin/env bash
set -euo pipefail
if [[ $# -gt 0 ]]; then
  mapfile -t FILES < <(printf '%s\n' "$@")
else
  mapfile -t FILES < <(git ls-files)
fi
if [[ ${#FILES[@]} -eq 0 ]]; then
  exit 0
fi
PATTERNS=(
  "Bearer [A-Za-z0-9\\-_.=:+/]{20,}"
  "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"
  "\b[0-9a-fA-F]{40,}\b"
  "\b[A-Za-z0-9+/]{40,}={0,2}\b"
  "AKIA[0-9A-Z]{16}"
)
ALLOW=${SENTIENTOS_SECRET_ALLOW:-}
for pattern in "${PATTERNS[@]}"; do
  if [[ -n $ALLOW && $pattern =~ $ALLOW ]]; then
    continue
  fi
  if command -v rg >/dev/null 2>&1; then
    matches=$(rg --files-with-matches --no-messages --text "$pattern" "${FILES[@]}" || true)
  else
    matches=$(grep -E -I -l -- "$pattern" "${FILES[@]}" 2>/dev/null || true)
  fi
  if [[ -n $matches ]]; then
    printf '%s\n' "$matches"
    echo "Potential secret detected for pattern: $pattern" >&2
    exit 1
  fi
done
exit 0
