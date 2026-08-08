from __future__ import annotations
import argparse,json
from typing import Any, Sequence, cast
from pathlib import Path
from sentientos import maintenance_windows_live_bootstrap as bootstrap

def _load(path:str) -> dict[str, Any]: return cast(dict[str, Any], json.loads(Path(path).read_text(encoding="utf-8")))
def main(argv: Sequence[str] | None = None) -> int:
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest="command",required=True)
 q=s.add_parser("write-template");q.add_argument("--output",required=True)
 q=s.add_parser("inspect-host");q.add_argument("--repository-root",required=True)
 q=s.add_parser("render");q.add_argument("--manifest",required=True);q.add_argument("--host-inspection",required=True);q.add_argument("--output-directory",required=True);q.add_argument("--create-custody-directories",action="store_true")
 q=s.add_parser("verify");q.add_argument("--index",required=True);q.add_argument("--evaluation-time",required=True)
 q=s.add_parser("inspect");q.add_argument("--index",required=True)
 q=s.add_parser("print-preflight-command");q.add_argument("--index",required=True)
 a=p.parse_args(argv)
 if a.command=="write-template":
  data=bootstrap.canonical_bytes(bootstrap.template());path=Path(a.output)
  if path.exists() and path.read_bytes()!=data: raise ValueError("template_output_conflict")
  path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);result={"status":"template_no_authority","output":str(path)}
 elif a.command=="inspect-host":result=bootstrap.inspect_host(a.repository_root)
 elif a.command=="render":result=bootstrap.render(_load(a.manifest),_load(a.host_inspection),a.output_directory,create_custody_directories=a.create_custody_directories)
 elif a.command=="verify":result=bootstrap.verify(a.index,evaluation_time=a.evaluation_time)
 elif a.command=="inspect":result=bootstrap.inspect(a.index)
 else:result=bootstrap.print_preflight_command(a.index)
 print(bootstrap.canonical_bytes(result).decode(),end="");return 0 if result.get("status")!=bootstrap.STATUS_BLOCKED else 1
if __name__=="__main__":raise SystemExit(main())
