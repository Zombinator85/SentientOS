set -euo pipefail
src=/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next
out="$src/artifacts/experiments/identity-neutral-journal-recovery-20261125-observation-scoped-v2"
workspace=/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl
exec env \
  SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE="$workspace" \
  SENTIENTOS_SOURCE_PROVENANCE_GIT="/mnt/c/Program Files/Git/cmd/git.exe" \
  SENTIENTOS_HERMES_MODEL="hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M" \
  SENTIENTOS_HERMES_MODEL_MANIFEST_PATH="$workspace/sentientos-data/rootless-experimental/ollama-model-manifests/ebb2efeea46036ca7f276589e710729aff06c3a4b7b7b970c09da1712daf0989.json" \
  SENTIENTOS_HERMES_GPU_LAYERS=32 \
  SENTIENTOS_HERMES_CYCLE_ID=rootless-cognition-cycle-d7a6c1108e52f0a394b7 \
  SENTIENTOS_HERMES_EXPERIMENT_SEED=13688611 \
  SENTIENTOS_HERMES_BACKEND_SEED=42 \
  SENTIENTOS_HERMES_PREREGISTRATION_DIGEST=3a40a583546cb03d7303e8ec4fbf8fc348b406b72c4f1cffbc0064eee3250ed5 \
  SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT="$workspace/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009/resident-cognition/history" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_PLAN_PATH="$out/execution_retry_independent_v2.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_COHORT_PATH="$out/cohort_bound.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_ANALYSIS_PATH="$out/analysis_independent_v2.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_JOURNAL_ROOT="$workspace/sentientos-data/rootless-experimental/cognition-preflight-private/20261125-observation-scoped-v2" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_PARITY_AUDIT_PATH="$out/parity_13688611.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_ALLOWLIST_PATH="$out/allowlist_13688611.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_VERIFICATION_PATH="$out/matched_pair_13688611.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_PATH="$out/hermes_13688611_preflight.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_PATH="$out/qwen_13688611_preflight.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_PATH="$out/hermes_13688611_preflight.json.verified.json" \
  SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_PATH="$out/qwen_13688611_preflight.json.verified.json" \
  "$workspace/.venv-cognition-cycle/bin/python" "$src/scripts/run_rootless_ollama_embodied_cognition_cycle.py"
