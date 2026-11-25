from pathlib import Path
import hashlib, json
base = Path('/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next/artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1')
state = Path('/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental')
plan = json.loads((base/'execution_independent_v2.json').read_text())
rows = []
for trial in plan['trials']:
    run_id = trial['runner_cycle_id']
    matches = list((state/'preflight-failures').glob(run_id+'-model-identity-*.json'))
    if len(matches) != 1:
        raise SystemExit(f'identity_preflight_evidence_count_invalid:{run_id}')
    path = matches[0]
    raw = path.read_bytes()
    report = json.loads(raw)
    if (report.get('schema_version') != 'sentientos.historical_examples_pair_model_identity_preflight:v1'
            or report.get('run_id') != run_id
            or report.get('execution_plan_digest') != plan['execution_plan_digest']
            or report.get('target_model_identity_digest') != plan['target_model_identity_digest']
            or report.get('predicted_model_identity_digest') != plan['target_model_identity_digest']
            or report.get('status') != 'matched_without_model_load'
            or report.get('run_root_allocated') is not False
            or report.get('model_loaded') is not False
            or report.get('model_invoked') is not False):
        raise SystemExit(f'identity_preflight_evidence_invalid:{run_id}')
    rows.append({'trial_index': trial['trial_index'], 'task_generation_seed': trial['task_generation_seed'], 'runner_cycle_id': run_id, 'status': report['status'], 'target_model_identity_digest': report['target_model_identity_digest'], 'predicted_model_identity_digest': report['predicted_model_identity_digest'], 'evidence_path': str(path), 'evidence_file_sha256': 'sha256:'+hashlib.sha256(raw).hexdigest(), 'run_root_allocated': False, 'model_loaded': False, 'model_invoked': False})
semantic = {'schema_version':'sentientos.historical_examples_pair_model_identity_preflight_cohort:v1','execution_plan_digest':plan['execution_plan_digest'],'trial_count':len(rows),'slots':rows,'all_identity_preflights_matched':True,'run_root_allocated':False,'model_loaded':False,'model_invoked':False,'learning_established':False,'authority':False}
canonical = json.dumps(semantic,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
value = {**semantic,'summary_digest':'sha256:'+hashlib.sha256(canonical).hexdigest()}
target = base/'runner_identity_preflights_v2.json'
with target.open('x',encoding='utf-8',newline='\n') as f:
    json.dump(value,f,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)
    f.write('\n')
print(json.dumps({'summary_digest':value['summary_digest'],'trial_count':len(rows),'all_identity_preflights_matched':True,'run_root_allocated':False,'model_loaded':False,'model_invoked':False},sort_keys=True))