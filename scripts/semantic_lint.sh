#!/usr/bin/env bash
set -euo pipefail
shopt -s nocasematch

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT"

WHITELIST=(
  "SEMANTIC_GLOSSARY.md"
  "SEMANTIC_REGRESSION_RULES.md"
)

PATTERNS=(
  "(^|[^a-zA-Z])wants([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])desires([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])seeks([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])tries to([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])survive([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])stay alive([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])continue existing([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])bond([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])relationship([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])connection([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])reward([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])punish([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])reinforce([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])heartbeat([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])trust([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])feels([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])cares([^a-zA-Z]|$)"
  "(^|[^a-zA-Z])loves([^a-zA-Z]|$)"
)

base_ref=""
for candidate in origin/main origin/master main master; do
  if git show-ref --quiet "$candidate"; then
    base_ref="$candidate"
    break
  fi
done

mapfile -t files < <(git diff --name-only --diff-filter=ACMRTUXB "${base_ref:+$base_ref...}HEAD" 2>/dev/null || true)
if [[ ${#files[@]} -eq 0 ]]; then
  mapfile -t files < <(git diff --name-only --cached --diff-filter=ACMRTUXB || true)
fi
if [[ ${#files[@]} -eq 0 ]]; then
  mapfile -t files < <(git ls-files)
fi

is_whitelisted() {
  local path="$1"
  for allowed in "${WHITELIST[@]}"; do
    if [[ "$path" == "$allowed" ]]; then
      return 0
    fi
  done
  return 1
}

hits=()

scan_file() {
  local file="$1"
  local diff_output=""

  if [[ -n "$base_ref" ]]; then
    diff_output=$(git diff --color=never --unified=0 "$base_ref...HEAD" -- "$file" 2>/dev/null || true)
  else
    diff_output=$(git diff --color=never --unified=0 HEAD -- "$file" 2>/dev/null || true)
  fi

  if [[ -z "$diff_output" ]]; then
    diff_output=$(git diff --color=never --unified=0 -- "$file" 2>/dev/null || true)
  fi

  if [[ -z "$diff_output" ]]; then
    return
  fi

  while IFS= read -r line; do
    [[ "$line" =~ ^\+\+\+ ]] && continue
    [[ "$line" =~ ^\+ ]] || continue
    local added_line="${line#+}"
    [[ "$added_line" == *"SEMANTIC_GLOSSARY.md#"* ]] && continue
    for pattern in "${PATTERNS[@]}"; do
      if [[ "$added_line" =~ $pattern ]]; then
        hits+=("$file: $added_line")
      fi
    done
  done <<< "$diff_output"
}

for file in "${files[@]}"; do
  [[ -f "$file" ]] || continue
  is_whitelisted "$file" && continue
  scan_file "$file"
done

if [[ ${#hits[@]} -gt 0 ]]; then
  echo "Semantic regression check failed. Forbidden language detected in added lines:" >&2
  printf ' - %s\n' "${hits[@]}" >&2
  echo "Use SEMANTIC_GLOSSARY.md anchors for frozen meanings or neutral substitutes listed in SEMANTIC_REGRESSION_RULES.md." >&2
  exit 1
fi

echo "Semantic regression check passed."
