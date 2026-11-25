set -euo pipefail
src=/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next
out="$src/artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1"
py=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/.venv-cognition-cycle/bin/python
cycle=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009
key=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-identity-neutral-v4/task-commitment.key
for seed in 13688505 13688506; do
  "$py" "$src/analysis/verify_matched_task_commitment_pair.py" --left-report "$out/hermes_${seed}_initial.json" --right-report "$out/qwen_${seed}_initial.json" --key-file "$key" --output "$out/matched_pair_${seed}_bootstrap.json"
  "$py" "$src/analysis/audit_matched_task_commitment_prompt_parity.py" --pair-verification "$out/matched_pair_${seed}_bootstrap.json" --left-report "$out/hermes_${seed}_initial.json" --right-report "$out/qwen_${seed}_initial.json" --left-preflight-verification "$out/hermes_${seed}_initial.json.verified.json" --right-preflight-verification "$out/qwen_${seed}_initial.json.verified.json" --cycle-root "$cycle" --output "$out/parity_${seed}_bootstrap.json"
  "$py" "$src/analysis/create_matched_history_record_allowlist.py" --parity-audit "$out/parity_${seed}_bootstrap.json" --output "$out/allowlist_${seed}.json"
done