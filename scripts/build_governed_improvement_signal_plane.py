#!/usr/bin/env python
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from sentientos.governed_improvement_signal_plane import evaluate_signal_plane, load_json_records, atomic_write_json, render_markdown, validate_evaluation

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd", required=True)
    b=sub.add_parser("build"); b.add_argument("--input", action="append", default=[]); b.add_argument("--repo-root", default="."); b.add_argument("--json-output"); b.add_argument("--markdown-output"); b.add_argument("--summary", action="store_true")
    v=sub.add_parser("validate"); v.add_argument("path")
    i=sub.add_parser("inspect-fixtures"); i.add_argument("fixture_root", nargs="?", default="tests/fixtures/governed_improvement_signal_plane")
    a=p.parse_args(argv)
    try:
        if a.cmd=="build":
            signals=load_json_records([Path(x) for x in a.input], repo_root=Path(a.repo_root)) if a.input else []
            ev=evaluate_signal_plane(signals, repo_root=Path(a.repo_root)); payload=ev.to_dict()
            if a.json_output: atomic_write_json(a.json_output, payload)
            if a.markdown_output:
                Path(a.markdown_output).parent.mkdir(parents=True, exist_ok=True); Path(a.markdown_output).write_text(render_markdown(ev), encoding="utf-8")
            if a.summary or not (a.json_output or a.markdown_output): print(json.dumps(payload["summary"], sort_keys=True))
            return 2 if payload["summary"].get("blocked_invalid_count") else 0
        if a.cmd=="validate":
            payload=json.loads(Path(a.path).read_text()); ok,reasons=validate_evaluation(payload); print(json.dumps({"ok":ok,"reasons":reasons}, sort_keys=True)); return 0 if ok else 2
        root=Path(a.fixture_root); print(json.dumps(sorted(str(p.relative_to(root)) for p in root.glob("*.json")))) ; return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"input_error:{exc}", file=sys.stderr); return 64
if __name__ == "__main__": raise SystemExit(main())
