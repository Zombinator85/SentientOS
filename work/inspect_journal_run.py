import json
from pathlib import Path
run=Path("/home/zombinator/.local/state/sentientos-cognition-followup-20261120-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-334cf5be6f3a415e9ce8")
f=json.loads((run/"cycle-failure.json").read_text())
print("failure",json.dumps({k:f.get(k) for k in ("run_id","stage","failure_code","failure_cause_code","failure_diagnostic","external_preregistration_digest","run_preregistration_digest","governed_unload","gpu_after")},sort_keys=True))
print("receipts",len(f.get("inference_receipts",[])))
print("stages",[(p.name,json.loads(p.read_text()).get("stage")) for p in sorted(run.glob("stage-checkpoint-*.json"))])
runs=run/"resident-cognition/state/developmental_experiments/runs"
for p in sorted(runs.glob("*.json")):
 x=json.loads(p.read_text()); protocol=x.get("protocol") or {}; task=protocol.get("objective_task_descriptor") or {}; e=x.get("objective_evaluation") or {}
 print("objective",json.dumps({"file":p.name,"inputs":task.get("probe_inputs"),"training":task.get("synthetic_training_observations"),"correct_counts":e.get("condition_correct_counts"),"history_delta":e.get("history_correct_probe_delta"),"restoration_delta":e.get("restoration_correct_probe_delta"),"summary":x.get("summary",{}).get("classification")},sort_keys=True))

