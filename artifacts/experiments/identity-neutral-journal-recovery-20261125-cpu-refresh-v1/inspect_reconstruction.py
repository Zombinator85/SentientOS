from pathlib import Path
import json, sys
sys.path.insert(0, '/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next')
from scripts.preflight_resident_historical_examples_pair import build_preflight, _read_private_task_commitment_key
from sentientos.developmental_history_intervention_experiment import DevelopmentalExperimentStore
from sentientos.developmental_model_replacement_experiment import derive_rootless_task_commitment_nonces
from work.historical_examples_intervention import HistoricalExamplesPairJournal
root=Path('/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental')
workspace=Path('/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next')
report_path=workspace/'artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/hermes_13688505_final.json'
report=json.loads(report_path.read_text())
key_path=root/'cognition-preflight-private/20261125-identity-neutral-v4/task-commitment.key'
key,key_digest=_read_private_task_commitment_key(key_path)
nonces=derive_rootless_task_commitment_nonces(key,seed=report['task_generation_seed'],task_family_id=report['task_family_id'])
journal_root=root/'cognition-preflight-private/20261125-identity-neutral-cpu-refresh-v1'
journal=HistoricalExamplesPairJournal(store=DevelopmentalExperimentStore(journal_root))
task=journal.load_task_for_protocol(protocol_digest=report['protocol_digest'])
rebuilt=build_preflight(cycle_root=root/'developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009',seed=report['task_generation_seed'],journal_root=journal_root,plan_path=workspace/'artifacts/experiments/rootless-history-campaign-0e68855964bb43179daf-hermes/plan_v1.json',model_identity_backend_seed=42,history_record_allowlist_file=workspace/'artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/allowlist_13688505.json',objective_task=task,task_commitment_nonces=nonces,task_commitment_key_file_sha256=key_digest,allow_recomputed_campaign_source_pin_mismatch=True,history_prompt_identity_policy=report['history_prompt_identity_policy'],authority_map_observed_at=report.get('authority_map_observed_at'),arm_order_seed=report['arm_order_seed'])
print('different_keys', [k for k in report if report.get(k)!=rebuilt.get(k)])
for k in report:
    if report.get(k)!=rebuilt.get(k):
        print(k,'report=',str(report.get(k))[:300],'rebuilt=',str(rebuilt.get(k))[:300])