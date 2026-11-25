import json
from pathlib import Path
run=Path("/home/zombinator/.local/state/sentientos-cognition-followup-20261120-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-1e3f877fb56242c5b2c0")
x=json.loads((run/"cycle-result.json").read_text())
for key in ("objective_task_family_acquisition","objective_task_family_transfer","history_transfer_intervention","later_companion_decision_intervention","developmental_outcome_assessment"):
 v=x.get(key)
 if not isinstance(v,dict): print(key,None); continue
 obj={"status":v.get("status"),"classification":v.get("classification"),"response_text_classification":v.get("response_text_classification"),"semantic_decision_classification":v.get("semantic_decision_classification")}
 ev=v.get("evaluation") or v.get("summary")
 if isinstance(ev,dict): obj["score_counts"]=ev.get("condition_correct_counts"); obj["history_delta"]=ev.get("history_correct_probe_delta")
 obj["conditions"]=[{k:c.get(k) for k in ("condition_id","decision_validation_status","decision_validation_error_code","disposition","disposition_normalization","history_record_ids","retrieved_record_ids")} for c in v.get("conditions",[]) if isinstance(c,dict)]
 obj["semantic_decisions"]=v.get("semantic_decisions")
 obj["governed_unload"]=v.get("governed_unload")
 print(key,json.dumps(obj,sort_keys=True))
print("run",json.dumps({k:x.get(k) for k in ("status","run_id","external_preregistration_digest","run_preregistration_digest")},sort_keys=True))
print("stage_files",[p.name for p in sorted(run.glob("stage-checkpoint-*.json"))])
