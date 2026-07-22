#!/usr/bin/env python3
"""CLI for metadata-only host dry-run audit closure runtime bundles."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Mapping
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.host_dry_run_audit_closure_runtime import HostDryRunAuditClosureRuntimeCoordinator, load_latest_evaluation, render_markdown, summarize_evaluation, validate_evaluation, validate_persisted_closure_bundle


def _ev(args: argparse.Namespace) -> Any:
    if args.bundle:
        v = validate_persisted_closure_bundle(Path(args.bundle))
        if not v.ok or v.evaluation is None:
            raise SystemExit(json.dumps(v.to_dict(), sort_keys=True))
        return v.evaluation
    if args.output_root and args.cmd in {"summarize", "render-json", "render-markdown", "validate-bundle"}:
        ev = load_latest_evaluation(args.output_root)
        if ev is not None: return ev
    if not (args.dry_run_runtime_bundle_root and args.output_root):
        raise SystemExit(f"{args.cmd} requires --dry-run-runtime-bundle-root --output-root")
    return HostDryRunAuditClosureRuntimeCoordinator().evaluate(dry_run_runtime_bundle_root=args.dry_run_runtime_bundle_root, output_root=args.output_root, correlation_id=args.correlation_id, persist=args.cmd == "close-audit")

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description="Build/inspect replay-safe host dry-run audit closure runtime bundles.")
    sub=p.add_subparsers(dest="cmd", required=False)
    for name in ("validate-source", "build-request", "plan", "close-audit", "validate-evaluation", "validate-bundle", "summarize", "render-json", "render-markdown", "diff"):
        sp=sub.add_parser(name)
        sp.add_argument("--dry-run-runtime-bundle-root")
        sp.add_argument("--output-root")
        sp.add_argument("--bundle")
        sp.add_argument("--output")
        sp.add_argument("--correlation-id")
    args=p.parse_args(argv)
    if args.cmd is None:
        p.print_help(); return 0
    out: Mapping[str, Any] | None = None
    if args.cmd == "diff":
        out={"status":"diff_not_applicable", "metadata_only": True, "simulation_only": True}
    elif args.cmd == "validate-source":
        c=HostDryRunAuditClosureRuntimeCoordinator(); _source, manifest, findings = c._read_source_bundle(args.dry_run_runtime_bundle_root or "")
        out={"ok": not findings, "findings": findings, "source_manifest": manifest}
    elif args.cmd == "validate-bundle":
        if args.bundle: out=validate_persisted_closure_bundle(args.bundle).to_dict()
        elif args.output_root:
            latest=Path(args.output_root)/"latest.json"
            data=json.loads(latest.read_text(encoding="utf-8")); out=validate_persisted_closure_bundle(Path(args.output_root)/str(data.get("request_id", "")), expected_final_digest=str(data.get("bundle_digest", "")), expected_request_id=str(data.get("request_id", ""))).to_dict()
        else:
            ev=_ev(args); out=validate_evaluation(ev).to_dict()
    else:
        ev=_ev(args)
        if args.cmd == "build-request": out=ev.request.to_dict() if ev.request else {"status": ev.status, "findings": ev.findings}
        elif args.cmd == "plan": out=ev.plan.to_dict() if ev.plan else {"status": ev.status, "findings": ev.findings}
        elif args.cmd == "validate-evaluation": out=validate_evaluation(ev).to_dict()
        elif args.cmd == "summarize": out=summarize_evaluation(ev)
        elif args.cmd == "render-markdown":
            text=render_markdown(ev)
            if args.output: Path(args.output).write_text(text, encoding="utf-8")
            else: print(text, end="")
            return 0
        else: out=ev.to_dict()
    text=json.dumps(out, sort_keys=True, indent=2)
    if args.output: Path(args.output).write_text(text, encoding="utf-8")
    else: print(text)
    return 0 if not (isinstance(out, dict) and out.get("ok") is False and args.cmd in {"validate-source", "validate-bundle", "validate-evaluation"}) else 1
if __name__ == "__main__": raise SystemExit(main())
