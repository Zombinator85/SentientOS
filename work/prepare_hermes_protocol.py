import hashlib,json,os,random,subprocess
from datetime import datetime,timezone
from pathlib import Path
base=Path("/home/zombinator/.local/state/sentientos-cognition-followup-20261120-wsl")
src=Path("/home/zombinator/.local/state/sentientos-hermes-cognition-campaign-20261119-wsl/source-cognition-next")
seed=2718281828
prior_digest="62e1f4646eb1b4e98a8842c807f1ca6f075562920298dbfda6ceef5b746de006"
template=json.loads((base/"protocols/hermes-developmental-cycle-20261120-1894517263.json").read_text())
r=random.Random(seed)
multiplier=r.randrange(2,4)
offset=r.randrange(0,3)
acquisition=sorted(r.sample(range(2,6),3))
transfer=sorted(r.sample(range(6,10),3))
status=subprocess.run(["git","status","--porcelain=v1","-z","--untracked-files=all"],cwd=src,check=True,capture_output=True).stdout
content=subprocess.run(["git","diff","--binary","--no-ext-diff","--no-textconv","HEAD"],cwd=src,check=True,capture_output=True).stdout
revision=subprocess.run(["git","rev-parse","--verify","HEAD"],cwd=src,check=True,capture_output=True,text=True).stdout.strip()
resident=hashlib.sha256((src/"sentientos/resident_developmental_cognition.py").read_bytes()).hexdigest()
runner=hashlib.sha256((src/"scripts/run_rootless_ollama_embodied_cognition_cycle.py").read_bytes()).hexdigest()
x=template
x["experiment_id"]=f"hermes-developmental-cycle-20261120-{seed}"
x["preregistered_at_utc"]=datetime.now(timezone.utc).isoformat()
x["resource_and_stop_rules"]["prior_attempt_reference"]={"outcome":"withheld_history_condition_rejected_unavailable_record_citation_before_restoration","protocol_digest":prior_digest,"reuse":False,"seed":3417259085}
x["runtime"]["requested_gpu_layers"]=32
x["source"]={"repository_revision":revision,"resident_cognition_sha256":resident,"runner_sha256":runner,"worktree_content_diff_digest":hashlib.sha256(content).hexdigest(),"worktree_status_digest":hashlib.sha256(status).hexdigest()}
x["task"].update({"task_generation_seed":seed,"multiplier":multiplier,"offset":offset,"acquisition_inputs":acquisition,"acquisition_targets":[multiplier*i+offset for i in acquisition],"transfer_inputs":transfer,"transfer_targets":[multiplier*i+offset for i in transfer]})
x.pop("protocol_digest",None)
x["protocol_digest"]=hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
p=base/"protocols"/f"hermes-developmental-cycle-20261120-{seed}.json"
with p.open("x",encoding="utf-8") as f:
    f.write(json.dumps(x,sort_keys=True,indent=2)+"\n")
os.chmod(p,0o600)
print(json.dumps({"path":str(p),"protocol_digest":x["protocol_digest"],"source":x["source"],"task":x["task"],"gpu_layers":x["runtime"]["requested_gpu_layers"]},sort_keys=True,indent=2))
