set -euo pipefail
export SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl
src=/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next
out="$src/artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1"
py=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/.venv-cognition-cycle/bin/python
cycle=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009
journal=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-identity-neutral-cpu-refresh-v1
key=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-identity-neutral-v4/task-commitment.key
plan="$src/artifacts/experiments/rootless-history-campaign-0e68855964bb43179daf-hermes/plan_v1.json"
root=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles
id1=rootless-cognition-cycle-b760d151071a42c799b1
id2=rootless-cognition-cycle-2afe5c4a5b854650b872
test ! -e "$root/$id1"
test ! -e "$root/$id2"
"$py" "$src/scripts/audit_historical_examples_pair_preflight_cohort.py" --journal-root "$journal" --cycle-root "$cycle" --plan "$plan" --output "$out/cohort_bound.json" --verifications "$out/hermes_13688505_bound.json.verified.json" "$out/hermes_13688506_bound.json.verified.json" --history-record-allowlist-files "$out/allowlist_13688505.json" "$out/allowlist_13688506.json" --shared-task-commitment-key-file "$key" --allow-recomputed-identity-recipe "$out/hermes_13688505_bound.json" "$out/hermes_13688506_bound.json"
"$py" "$src/scripts/freeze_historical_examples_pair_analysis.py" --cohort "$out/cohort_bound.json" --output "$out/analysis_bound.json"
"$py" "$src/scripts/freeze_historical_examples_pair_analysis.py" --cohort "$out/cohort_bound.json" --verify-plan "$out/analysis_bound.json"
"$py" "$src/scripts/freeze_historical_examples_pair_execution.py" --cohort "$out/cohort_bound.json" --analysis-plan "$out/analysis_bound.json" --runner-cycle-id "$id1" --runner-cycle-id "$id2" --backend-seed 42 --output "$out/execution_bound.json"
"$py" "$src/scripts/freeze_historical_examples_pair_execution.py" --cohort "$out/cohort_bound.json" --analysis-plan "$out/analysis_bound.json" --runner-cycle-id "$id1" --runner-cycle-id "$id2" --backend-seed 42 --verify-plan "$out/execution_bound.json"
"$py" "$src/scripts/verify_historical_examples_pair_execution_slots.py" --cohort "$out/cohort_bound.json" --analysis-plan "$out/analysis_bound.json" --plan "$out/execution_bound.json" --journal-root "$journal" --output "$out/execution_slots_verified.json"