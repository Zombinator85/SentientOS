from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Mapping, cast
from sentientos.household_presence_camera_zone_config import build_default_config
from sentientos.household_presence_camera_zone_resolver import HouseholdCameraZoneResolverPolicy, dumps_result, resolve_camera_event_zone

def _load(path: str) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], json.loads(Path(path).read_text()))

def main() -> int:
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
    for c in ('build-default','resolve','validate','summarize','inspect-fixture'):
        s=sp.add_parser(c); s.add_argument('--config'); s.add_argument('--event'); s.add_argument('--input'); s.add_argument('--fixtures-dir',default='tests/fixtures/household_presence_camera_zone_resolver'); s.add_argument('--output'); s.add_argument('--summary',action='store_true')
    a=ap.parse_args()
    if a.cmd=='build-default':
        out={'zones':build_default_config()}
        text=json.dumps(out,indent=2,sort_keys=True)
        if a.output: Path(a.output).write_text(text+'\n')
        print(text); return 0
    if a.cmd=='inspect-fixture':
        event=_load(str(Path(a.fixtures_dir)/str(a.input))); config={'zones':build_default_config()}
    elif a.cmd in {'resolve','validate','summarize'}:
        event=_load(a.event if a.event else a.input); config=_load(a.config) if a.config else {'zones':build_default_config()}
    result=resolve_camera_event_zone(config,event,HouseholdCameraZoneResolverPolicy())
    out={'status':result.report.status,'effective_zone':result.resolution.effective_zone,'warnings':list(result.report.warnings)} if (a.summary or a.cmd=='summarize') else json.loads(dumps_result(result))
    text=json.dumps(out,indent=2,sort_keys=True)
    if a.output: Path(a.output).write_text(text+'\n')
    print(text)
    return 1 if result.report.status in {'blocked','review_required'} and a.cmd in {'resolve','validate','inspect-fixture'} else 0
if __name__=='__main__': raise SystemExit(main())
