set -euo pipefail
src=/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next
out="$src/artifacts/experiments/identity-neutral-journal-recovery-20261125-terminal-binding-v1"
py=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/.venv-cognition-cycle/bin/python
journal=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-terminal-binding-v1
plan="$out/execution_independent_v2.json"
"$py" "$src/scripts/freeze_historical_examples_pair_execution.py" --cohort "$out/cohort_bound.json" --analysis-plan "$out/analysis_independent_v2.json" --runner-cycle-id rootless-cognition-cycle-4c92d1be70a8f5631d29 --runner-cycle-id rootless-cognition-cycle-6e35a0c98f1d72b4a603 --backend-seed 42 --output "$plan"
"$py" "$src/scripts/freeze_historical_examples_pair_execution.py" --cohort "$out/cohort_bound.json" --analysis-plan "$out/analysis_independent_v2.json" --runner-cycle-id rootless-cognition-cycle-4c92d1be70a8f5631d29 --runner-cycle-id rootless-cognition-cycle-6e35a0c98f1d72b4a603 --backend-seed 42 --verify-plan "$plan"
"$py" "$src/scripts/verify_historical_examples_pair_execution_slots.py" --cohort "$out/cohort_bound.json" --analysis-plan "$out/analysis_independent_v2.json" --plan "$plan" --journal-root "$journal" --output "$out/execution_slots_verified_v2.json"
