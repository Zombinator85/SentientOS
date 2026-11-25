import json
from pathlib import Path
p=Path("/home/zombinator/.local/state/sentientos-cognition-followup-20261120-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-fc801d38eb324274bf32/preregistration.json")
x=json.loads(p.read_text())
print(json.dumps({k:x.get(k) for k in ("external_protocol_digest","experiment_seed","history_order_trial_index","preregistration_digest","model_manifest_digest","gpu_layers_requested","source_provenance")},sort_keys=True,indent=2))
