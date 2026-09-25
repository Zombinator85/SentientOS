from __future__ import annotations
import argparse,json
from pathlib import Path
from sentientos.resident_cognitive_model_transition_rehearsal import run

def main()->int:
 p=argparse.ArgumentParser();p.add_argument("run",nargs="?");p.add_argument("--root",required=True,type=Path);p.add_argument("--summary",action="store_true");a=p.parse_args()
 result=run(a.root);print(json.dumps(result,sort_keys=True) if a.summary else result["status"]);return 0
if __name__=="__main__":raise SystemExit(main())
