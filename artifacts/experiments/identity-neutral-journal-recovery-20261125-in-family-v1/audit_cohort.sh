set -euo pipefail
export SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl
src=/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next
out="$src/artifacts/experiments/identity-neutral-journal-recovery-20261125-in-family-v1"
py=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/.venv-cognition-cycle/bin/python
cycle=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009
journal=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-in-family-v1
key=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-identity-neutral-v4/task-commitment.key
plan="$src/artifacts/experiments/rootless-history-campaign-0e68855964bb43179daf-hermes/plan_v1.json"
for seed in 13688701 13688702; do
  "$py" "$src/analysis/verify_matched_task_commitment_pair.py" --left-report "$out/hermes_${seed}_preflight.json" --right-report "$out/qwen_${seed}_preflight.json" --key-file "$key" --output "$out/matched_pair_${seed}.json"
  "$py" "$src/analysis/audit_matched_task_commitment_prompt_parity.py" --pair-verification "$out/matched_pair_${seed}.json" --left-report "$out/hermes_${seed}_preflight.json" --right-report "$out/qwen_${seed}_preflight.json" --left-preflight-verification "$out/hermes_${seed}_preflight.json.verified.json" --right-preflight-verification "$out/qwen_${seed}_preflight.json.verified.json" --cycle-root "$cycle" --output "$out/parity_${seed}.json"
done
"$py" "$src/scripts/audit_historical_examples_pair_preflight_cohort.py" --journal-root "$journal" --cycle-root "$cycle" --plan "$plan" --output "$out/cohort_bound.json" --verifications "$out/hermes_13688701_preflight.json.verified.json" "$out/hermes_13688702_preflight.json.verified.json" --history-record-allowlist-files "$out/allowlist_13688701.json" "$out/allowlist_13688702.json" --shared-task-commitment-key-file "$key" --allow-recomputed-identity-recipe "$out/hermes_13688701_preflight.json" "$out/hermes_13688702_preflight.json"
"$py" "$src/scripts/freeze_historical_examples_pair_analysis.py" --cohort "$out/cohort_bound.json" --output "$out/analysis_independent_v2.json"
"$py" "$src/scripts/freeze_historical_examples_pair_analysis.py" --cohort "$out/cohort_bound.json" --verify-plan "$out/analysis_independent_v2.json"
