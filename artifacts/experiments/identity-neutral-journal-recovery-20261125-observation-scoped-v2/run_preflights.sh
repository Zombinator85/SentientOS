set -euo pipefail
export SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl
src=/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next
out="$src/artifacts/experiments/identity-neutral-journal-recovery-20261125-observation-scoped-v2"
py=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/.venv-cognition-cycle/bin/python
cycle=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009
journal=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-observation-scoped-v2
key=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-identity-neutral-v4/task-commitment.key
mkdir -p "$journal"
for seed in 13688611 13688612; do
  for model in hermes qwen; do
    if [ "$model" = hermes ]; then
      plan="$src/artifacts/experiments/rootless-history-campaign-0e68855964bb43179daf-hermes/plan_v1.json"
    else
      plan="$src/artifacts/experiments/rootless-history-campaign-0e68855964bb43179daf-qwen/plan_v1.json"
    fi
    report="$out/${model}_${seed}_preflight.json"
    "$py" "$src/scripts/preflight_resident_historical_examples_pair.py" --cycle-root "$cycle" --seed "$seed" --journal-root "$journal" --plan "$plan" --model-identity-backend-seed 42 --authority-map-observed-at 2026-11-23T00:00:00+00:00 --shared-task-commitment-key-file "$key" --history-record-allowlist-file "$out/allowlist_${seed}.json" --history-prompt-identity-policy matched_cross_model_identity_omitted:v1 --allow-recomputed-identity-recipe --output "$report"
    "$py" "$src/scripts/preflight_resident_historical_examples_pair.py" --cycle-root "$cycle" --seed "$seed" --journal-root "$journal" --plan "$plan" --model-identity-backend-seed 42 --authority-map-observed-at 2026-11-23T00:00:00+00:00 --shared-task-commitment-key-file "$key" --history-record-allowlist-file "$out/allowlist_${seed}.json" --history-prompt-identity-policy matched_cross_model_identity_omitted:v1 --allow-recomputed-identity-recipe --verify-report "$report" --verification-output "$report.verified.json"
  done
done
