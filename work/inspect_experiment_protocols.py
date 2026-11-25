import json
from pathlib import Path
root=Path("/home/zombinator/.local/state/sentientos-cognition-followup-20261120-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-fc801d38eb324274bf32/resident-cognition/state/developmental_experiments")
for p in sorted((root/"runs").glob("*.json")):
 x=json.loads(p.read_text()); pr=x.get("protocol",{})
 print(json.dumps({"file":p.name,"top_keys":list(x),"protocol_keys":list(pr),"objective_task":pr.get("objective_task_descriptor"),"objective_eval":x.get("objective_evaluation")},sort_keys=True))
