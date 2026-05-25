from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, cast
from sentientos.household_presence_camera_zone_config import build_default_config, validate_zone_config, dumps_result

def _load(p: Path) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(p.read_text()))

def main() -> int:
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
    for c in ("build-default","validate","summarize","inspect-fixture"):
        s=sp.add_parser(c); s.add_argument("--input"); s.add_argument("--fixtures-dir",default="tests/fixtures/household_presence_camera_zone_configs"); s.add_argument("--output"); s.add_argument("--summary",action="store_true")
    a=ap.parse_args(); payload: dict[str, list[dict[str, Any]]]
    if a.cmd=="build-default": payload={"zones":build_default_config()}
    elif a.cmd=="inspect-fixture": payload={"zones":_load(Path(a.fixtures_dir)/str(a.input))}
    else: payload={"zones":_load(Path(str(a.input)))}
    res=validate_zone_config(payload)
    out={"status":res.report.status,"sources":res.report.source_count,"zones":res.report.zone_count,"finding_codes":[f.code for f in res.report.findings]} if a.summary else json.loads(dumps_result(res))
    text=json.dumps(out,indent=2,sort_keys=True)
    if a.output: Path(a.output).write_text(text+"\n")
    print(text)
    return 1 if res.report.status=="blocked" and a.cmd in {"validate","inspect-fixture"} else 0
if __name__=="__main__": raise SystemExit(main())
