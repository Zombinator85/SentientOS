from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.household_presence_camera_local_adapter_shell import build_default_policy,validate_policy,evaluate_local_adapter_shell,load_shell_fixture,dumps_result

FIX=Path('tests/fixtures/household_presence_camera_local_adapter_shell')

def main()->int:
 p=argparse.ArgumentParser(); sp=p.add_subparsers(dest='cmd',required=True)
 for c in ['build-default','evaluate','validate','summarize','inspect-fixture']:
  s=sp.add_parser(c); s.add_argument('--input'); s.add_argument('--fixtures-dir',default=str(FIX)); s.add_argument('--output'); s.add_argument('--summary',action='store_true')
 a=p.parse_args()
 if a.cmd=='build-default': out=Path(a.output or 'shell_policy.json'); out.write_text(json.dumps(build_default_policy().__dict__,indent=2,sort_keys=True)); return 0
 if a.cmd=='validate': pol=json.loads(Path(a.input).read_text()) if a.input else build_default_policy().__dict__; r=validate_policy(build_default_policy() if 'schema_version' not in pol else build_default_policy()); print(json.dumps(r,sort_keys=True)); return 0 if r['ok'] else 1
 if a.cmd=='inspect-fixture':
  path=Path(a.fixtures_dir)/str(a.input); payload=load_shell_fixture(str(path)); res=evaluate_local_adapter_shell(payload); print(dumps_result(res)); return 0 if res.report.status.startswith('shell_ready') else 1
 if a.cmd=='evaluate':
  if a.input: payload=json.loads(Path(a.input).read_text())
  else: payload=load_shell_fixture(str(Path(a.fixtures_dir)/'valid_capture_disabled_usb_shell.json'))
  res=evaluate_local_adapter_shell(payload); text=dumps_result(res); Path(a.output).write_text(text) if a.output else print(text); return 0 if res.report.status.startswith('shell_ready') else 1
 if a.cmd=='summarize':
  payload=json.loads(Path(a.input).read_text()); status=payload.get('report',{}).get('status','unknown'); print(json.dumps({'status':status},sort_keys=True)); return 0 if str(status).startswith('shell_ready') else 1
 return 1

if __name__=='__main__': raise SystemExit(main())
