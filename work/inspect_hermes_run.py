import json
from pathlib import Path
root=Path("/home/zombinator/.local/state/sentientos-cognition-followup-20261120-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-fc801d38eb324274bf32")
for p in sorted((root/"inference-custody/receipts").glob("*.json"),key=lambda p:p.stat().st_mtime):
    try:
        x=json.loads(p.read_text())
    except Exception as e:
        print(p.name,"unreadable",type(e).__name__)
        continue
    req=x.get("request",{})
    print(json.dumps({"id":x.get("receipt_id"),"status":x.get("status"),"correlation_id":x.get("correlation_id") or req.get("correlation_id"),"started":x.get("invocation_started_at"),"finished":x.get("invocation_finished_at"),"output_digest":x.get("output_digest"),"output_bytes":x.get("output_size_bytes"),"effects":x.get("effects")},sort_keys=True))
print("run_files:")
for p in sorted(root.glob("*.json")): print(p.name)
