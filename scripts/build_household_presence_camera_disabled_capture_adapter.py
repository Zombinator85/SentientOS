from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.household_presence_camera_disabled_capture_adapter import build_default_policy, validate_policy, evaluate_disabled_capture, load_fixture

def _load(path: str) -> dict[str, object]: return dict(json.loads(Path(path).read_text()))

def main(argv: list[str] | None = None) -> int:
    a=argparse.ArgumentParser(); sub=a.add_subparsers(dest='cmd', required=True)
    b=sub.add_parser('build-default'); b.add_argument('--output', required=True)
    e=sub.add_parser('evaluate'); e.add_argument('--input'); e.add_argument('--fixtures-dir', default='tests/fixtures/household_presence_camera_disabled_capture_adapter'); e.add_argument('--fixture'); e.add_argument('--output'); e.add_argument('--summary', action='store_true')
    v=sub.add_parser('validate'); v.add_argument('--input', required=True)
    s=sub.add_parser('summarize'); s.add_argument('--input', required=True)
    i=sub.add_parser('inspect-fixture'); i.add_argument('--fixtures-dir', default='tests/fixtures/household_presence_camera_disabled_capture_adapter'); i.add_argument('--input', required=True)
    ns=a.parse_args(argv)
    if ns.cmd=='build-default': Path(ns.output).write_text(json.dumps(build_default_policy().__dict__, indent=2, sort_keys=True)); return 0
    if ns.cmd=='validate': return 0 if validate_policy(build_default_policy())['ok'] else 1
    if ns.cmd=='inspect-fixture': payload=load_fixture(str(Path(ns.fixtures_dir)/ns.input))
    elif ns.cmd in {'evaluate','summarize'}:
        if ns.input: payload=_load(ns.input)
        else: payload=load_fixture(str(Path(ns.fixtures_dir)/ns.fixture))
    r=evaluate_disabled_capture(payload).to_dict(); out=json.dumps(r, indent=2, sort_keys=True)
    if getattr(ns,'output',None): Path(ns.output).write_text(out)
    if ns.cmd=='summarize' or getattr(ns,'summary',False): print(json.dumps({'status':r['report']['status'],'digest':r['report']['deterministic_digest']}, sort_keys=True))
    else: print(out)
    return 1 if 'blocked' in r['report']['status'] or r['report']['status']=='disabled_capture_failed' else 0
if __name__=='__main__': raise SystemExit(main())
