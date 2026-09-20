#!/usr/bin/env bash
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd); cd "$ROOT"
CLAIMS='^[[:space:]*#>-]*(sentientos|the (current )?(system|runtime|model)|this (system|runtime|model)).{0,32}(is sentient|is conscious|is alive|feels|suffers|experiences (pain|pleasure))'
RESEARCH_OR_NEGATION='(not |does not |is not |no claim|not claimed|hypothes|research question|aspirational|if |whether |possible|may |might |could )'
base_ref=""; for candidate in origin/main origin/master main master; do git show-ref --quiet "$candidate" && { base_ref="$candidate"; break; }; done
if [[ -n "$base_ref" ]]; then diff=$(git diff --color=never --unified=0 "$base_ref...HEAD" 2>/dev/null || true); else diff=$(git diff --color=never --unified=0 HEAD 2>/dev/null || true); fi
[[ -n "$diff" ]] || diff=$(git diff --color=never --unified=0 2>/dev/null || true)
hits=(); while IFS= read -r line; do [[ "$line" == +++* || "$line" != +* ]] && continue; added=${line#+}; if printf '%s\n' "$added" | grep -Eiq "$CLAIMS" && ! printf '%s\n' "$added" | grep -Eiq "$RESEARCH_OR_NEGATION"; then hits+=("$added"); fi; done <<< "$diff"
if ((${#hits[@]})); then echo "Semantic regression check failed: unsupported present-tense phenomenal claim:" >&2; printf ' - %s\n' "${hits[@]}" >&2; exit 1; fi
echo "Semantic regression check passed."
