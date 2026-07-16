# mypy: disable-error-code="no-untyped-def,no-untyped-call,var-annotated,dict-item"
#!/usr/bin/env python3
"""Inspection-only CLI for the read-only world-state evidence board."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.world_state_board import WorldStateBoardBuilder, diff_snapshots, to_dict, validate_snapshot
from sentientos.world_state_sources import SourceDeclaration, build_snapshot_from_manifest

def _load_snapshot(path:Path):
    # For CLI inspection, rebuild from embedded records if present; otherwise empty.
    data=json.loads(path.read_text())
    records=data.get("records", []) if isinstance(data,dict) else []
    return WorldStateBoardBuilder().build(records)

def _print(obj, markdown=False):
    if markdown:
        print("# World State Board\n")
        if isinstance(obj,dict):
            for k,v in obj.items(): print(f"- **{k}**: `{v}`")
        else: print(json.dumps(obj, indent=2, sort_keys=True))
    else: print(json.dumps(obj, indent=2, sort_keys=True))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="cmd", required=True)
    for name in ["build","validate","summarize","list-sources","list-entities","show-entity","list-conflicts","diff","render-json","render-markdown","inspect-source"]:
        sp=sub.add_parser(name); sp.add_argument("--input"); sp.add_argument("--output"); sp.add_argument("--subject-id"); sp.add_argument("--source-id"); sp.add_argument("--before"); sp.add_argument("--after")
    a=p.parse_args(argv)
    if a.cmd=="diff": obj=to_dict(diff_snapshots(_load_snapshot(Path(a.before)), _load_snapshot(Path(a.after))))
    else:
        records=[]
        if a.input:
            data=json.loads(Path(a.input).read_text()); records=data if isinstance(data,list) else data.get("records",[])
        snap=WorldStateBoardBuilder().build(records)
        if a.cmd=="validate": obj=to_dict(validate_snapshot(snap))
        elif a.cmd=="summarize": obj=to_dict(snap.summary)
        elif a.cmd=="list-sources": obj=[to_dict(s) for s in snap.sources]
        elif a.cmd=="list-entities": obj=[to_dict(e) for e in snap.entities]
        elif a.cmd=="show-entity": obj=next((to_dict(e) for e in snap.entities if e.subject.subject_id==a.subject_id), {"error":"not_found"})
        elif a.cmd=="list-conflicts": obj=[to_dict(c) for c in snap.conflicts]
        elif a.cmd=="inspect-source": obj=next((to_dict(s) for s in snap.sources if s.source_id==a.source_id), {"error":"not_found"})
        elif a.cmd=="render-markdown": obj={"snapshot_id":snap.snapshot_id,"digest":snap.digest,"entities":len(snap.entities),"conflicts":len(snap.conflicts),"authority":snap.authority}
        else: obj=to_dict(snap)
    text=json.dumps(obj, indent=2, sort_keys=True)
    if a.cmd=="render-markdown":
        lines=["# World State Board", "", f"- Snapshot: `{obj['snapshot_id']}`", f"- Digest: `{obj['digest']}`", f"- Entities: `{obj['entities']}`", f"- Conflicts: `{obj['conflicts']}`", "- Authority: view-only / non-authoritative"]
        text="\n".join(lines)+"\n"
    if a.output: Path(a.output).write_text(text)
    else: print(text)
if __name__=="__main__": main()
