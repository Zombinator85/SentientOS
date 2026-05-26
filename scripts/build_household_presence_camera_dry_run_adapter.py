from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from sentientos.household_presence_camera_dry_run_adapter import build_default_policy, validate_policy, evaluate_dry_run_session, load_session_fixture

def _load(path: str) -> dict[str, Any]: return dict(json.loads(Path(path).read_text()))

def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(); sub = a.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-default"); b.add_argument("--output", required=True)
    rf = sub.add_parser("run-fixture"); rf.add_argument("--fixtures-dir", default="tests/fixtures/household_presence_camera_dry_run_adapter"); rf.add_argument("--input", required=True); rf.add_argument("--output"); rf.add_argument("--summary", action="store_true")
    rs = sub.add_parser("run-session"); rs.add_argument("--input", required=True); rs.add_argument("--output"); rs.add_argument("--summary", action="store_true")
    v = sub.add_parser("validate"); v.add_argument("--input", required=True)
    s = sub.add_parser("summarize"); s.add_argument("--input", required=True)
    i = sub.add_parser("inspect-fixture"); i.add_argument("--fixtures-dir", default="tests/fixtures/household_presence_camera_dry_run_adapter"); i.add_argument("--input", required=True)
    ns = a.parse_args(argv)
    if ns.cmd == "build-default": Path(ns.output).write_text(json.dumps(build_default_policy().__dict__, indent=2, sort_keys=True)); return 0
    if ns.cmd == "validate": return 0 if validate_policy(build_default_policy())["ok"] else 1
    if ns.cmd == "inspect-fixture": payload = load_session_fixture(str(Path(ns.fixtures_dir) / ns.input))
    elif ns.cmd in {"run-session", "summarize"}: payload = _load(ns.input)
    else: payload = load_session_fixture(str(Path(ns.fixtures_dir) / ns.input))
    result = evaluate_dry_run_session(payload).to_dict(); out = json.dumps(result, indent=2, sort_keys=True)
    if getattr(ns, "output", None): Path(ns.output).write_text(out)
    if ns.cmd == "summarize" or getattr(ns, "summary", False):
        print(json.dumps({"status": result["report"]["status"], "routes": result["report"]["route_counts"], "digest": result["report"]["deterministic_digest"]}, sort_keys=True))
    else:
        print(out)
    return 1 if result["report"]["status"] in {"dry_run_operator_confirmation_required", "dry_run_blocked", "dry_run_failed"} else 0

if __name__ == "__main__": raise SystemExit(main())
