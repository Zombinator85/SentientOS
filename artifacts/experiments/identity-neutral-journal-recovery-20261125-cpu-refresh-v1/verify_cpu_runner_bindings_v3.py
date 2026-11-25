from pathlib import Path
import hashlib, json, os, sys
repo=Path('/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next')
sys.path.insert(0,str(repo))
workspace=Path('/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl')
os.environ['SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE']=str(workspace)
from sentientos.developmental_history_intervention_experiment import DevelopmentalExperimentStore
from work.historical_examples_intervention import HistoricalExamplesPairJournal, _digest, validate_historical_examples_pair_execution_plan, validate_historical_examples_pair_execution_slot
from work.identity_neutral_history_binding import verify_identity_neutral_history_binding
base=repo/'artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1'
plan=json.loads((base/'execution_independent_v2.json').read_text())
cohort=json.loads((base/'cohort_bound.json').read_text())
analysis=json.loads((base/'analysis_independent_v2.json').read_text())
slot_audit=json.loads((base/'execution_slots_verified_v2.json').read_text())
identity_audit=json.loads((base/'runner_identity_preflights_v2.json').read_text())
identity_semantic={k:v for k,v in identity_audit.items() if k!='summary_digest'}
identity_digest='sha256:'+hashlib.sha256(json.dumps(identity_semantic,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
if (identity_audit.get('summary_digest')!=identity_digest or identity_audit.get('all_identity_preflights_matched') is not True or identity_audit.get('model_loaded') is not False or identity_audit.get('model_invoked') is not False or identity_audit.get('run_root_allocated') is not False):
    raise SystemExit('runner_identity_preflight_summary_invalid')
runner_ids=[row['runner_cycle_id'] for row in plan['trials']]
canonical_plan=validate_historical_examples_pair_execution_plan(cohort=cohort,analysis_plan=analysis,runner_cycle_ids=runner_ids,backend_seed=42,plan=plan)
if (slot_audit.get('execution_plan_digest')!=canonical_plan['execution_plan_digest'] or slot_audit.get('all_slots_verified') is not True or slot_audit.get('trial_count')!=len(canonical_plan['trials'])):
    raise SystemExit('execution_slot_audit_plan_binding_invalid')
source_cycle=workspace/'sentientos-data/rootless-experimental/developmental-cognition-cycles'/canonical_plan['source_cycle_root_id']
journal_root=workspace/'sentientos-data/rootless-experimental/cognition-preflight-private/20261125-identity-neutral-cpu-refresh-v1'
journal=HistoricalExamplesPairJournal(store=DevelopmentalExperimentStore(journal_root))
rows=[]
for index,trial in enumerate(canonical_plan['trials']):
    seed=trial['task_generation_seed']
    protocol=journal.load_protocol(protocol_digest=trial['protocol_digest'])
    task=journal.load_task_for_protocol(protocol_digest=trial['protocol_digest'])
    slot=validate_historical_examples_pair_execution_slot(plan=canonical_plan,trial_index=index,protocol=protocol,objective_task=task,runner_cycle_id=trial['runner_cycle_id'],backend_seed=42)
    report_names={key:base/f'{model}_{seed}_bound.json' for key,model in [('left','hermes'),('right','qwen')]}
    parity=base/f'parity_{seed}_bound.json'
    pair=base/f'matched_pair_{seed}_bound.json'
    allowlist=base/f'allowlist_{seed}.json'
    binding=verify_identity_neutral_history_binding(objective_task=task,protocol=protocol,target_identity_digest=canonical_plan['target_model_identity_digest'],parity_audit_path=str(parity),allowlist_path=str(allowlist),pair_verification_path=str(pair),left_preflight_path=str(report_names['left']),right_preflight_path=str(report_names['right']),left_preflight_verification_path=str(report_names['left'])+'.verified.json',right_preflight_verification_path=str(report_names['right'])+'.verified.json',source_cycle_root=source_cycle)
    identity=next((row for row in identity_audit['slots'] if row['runner_cycle_id']==trial['runner_cycle_id']),None)
    if (identity is None or identity.get('status')!='matched_without_model_load' or identity.get('target_model_identity_digest')!=canonical_plan['target_model_identity_digest'] or identity.get('predicted_model_identity_digest')!=canonical_plan['target_model_identity_digest'] or identity.get('model_loaded') is not False or identity.get('model_invoked') is not False):
        raise SystemExit('runner_identity_slot_binding_invalid')
    raw=Path(identity['evidence_path']).read_bytes()
    if 'sha256:'+hashlib.sha256(raw).hexdigest()!=identity['evidence_file_sha256']:
        raise SystemExit('runner_identity_receipt_digest_mismatch')
    private=json.loads(raw)
    if private.get('run_id')!=trial['runner_cycle_id'] or private.get('execution_plan_digest')!=canonical_plan['execution_plan_digest'] or private.get('status')!='matched_without_model_load' or private.get('model_loaded') is not False or private.get('model_invoked') is not False or private.get('run_root_allocated') is not False:
        raise SystemExit('runner_identity_receipt_binding_invalid')
    checkpoint=slot_audit['verified_slots'][index]
    if checkpoint.get('runner_cycle_id')!=trial['runner_cycle_id'] or checkpoint.get('protocol_digest')!=trial['protocol_digest'] or checkpoint.get('task_digest')!=trial['task_digest']:
        raise SystemExit('execution_slot_checkpoint_mismatch')
    rows.append({'trial_index':index,'task_generation_seed':seed,'runner_cycle_id':trial['runner_cycle_id'],'protocol_digest':trial['protocol_digest'],'task_digest':trial['task_digest'],'execution_slot_verified':True,'identity_neutral_history_binding':binding,'runner_identity_preflight_status':identity['status'],'runner_identity_evidence_sha256':identity['evidence_file_sha256'],'predicted_model_identity_digest':identity['predicted_model_identity_digest'],'target_model_identity_digest':identity['target_model_identity_digest'],'run_root_allocated':False,'model_loaded':False,'model_invoked':False,'learning_established':False,'authority':False})
semantic={'schema_version':'sentientos.historical_examples_pair_cpu_runner_binding_audit:v1','execution_plan_digest':canonical_plan['execution_plan_digest'],'cohort_digest':canonical_plan['cohort_digest'],'identity_preflight_summary_digest':identity_digest,'trial_count':len(rows),'slots':rows,'all_execution_slots_verified':True,'all_identity_neutral_bindings_verified':True,'all_model_identity_preflights_matched':True,'run_root_allocated':False,'model_loaded':False,'model_invoked':False,'learning_established':False,'authority':False}
body=json.dumps(semantic,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
value={**semantic,'audit_digest':'sha256:'+hashlib.sha256(body).hexdigest()}
target=base/'cpu_runner_binding_audit_v3.json'
with target.open('x',encoding='utf-8',newline='\n') as f:
    json.dump(value,f,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')
print(json.dumps({'audit_digest':value['audit_digest'],'trial_count':len(rows),'all_execution_slots_verified':True,'all_identity_neutral_bindings_verified':True,'all_model_identity_preflights_matched':True,'run_root_allocated':False,'model_loaded':False,'model_invoked':False,'learning_established':False},sort_keys=True))