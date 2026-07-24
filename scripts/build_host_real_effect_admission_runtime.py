#!/usr/bin/env python3
"""CLI for metadata-only host real-effect admission runtime bundles."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.host_real_effect_admission_runtime import HostRealEffectAdmissionRuntimeCoordinator, load_latest_evaluation, render_markdown, summarize_evaluation, validate_evaluation, validate_persisted_admission_bundle
from sentientos.host_dry_run_audit_closure_runtime import validate_persisted_closure_bundle

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description="Build/validate replay-safe host real-effect admission runtime evidence.")
    sub=p.add_subparsers(dest='cmd')
    for name in ('evaluate','validate-source','validate-bundle','latest-summary'):
        sp=sub.add_parser(name); sp.add_argument('--closure-bundle-root'); sp.add_argument('--output-root'); sp.add_argument('--bundle'); sp.add_argument('--output'); sp.add_argument('--correlation-id'); sp.add_argument('--admission-domain'); sp.add_argument('--requested-implementation-tier')
    args=p.parse_args(argv)
    if args.cmd is None: p.print_help(); return 0
    ok=True
    if args.cmd == 'validate-source':
        out=validate_persisted_closure_bundle(args.closure_bundle_root or '').to_dict(); ok=bool(out.get('ok'))
    elif args.cmd == 'validate-bundle':
        target=args.bundle
        if not target and args.output_root:
            latest=json.loads((Path(args.output_root)/'latest.json').read_text(encoding='utf-8')); target=Path(args.output_root)/str(latest.get('request_id',''))
        out=validate_persisted_admission_bundle(target or '').to_dict(); ok=bool(out.get('ok'))
    elif args.cmd == 'latest-summary':
        ev=load_latest_evaluation(args.output_root or '')
        if ev is None: out={'ok': False, 'findings': ['latest_validated_summary_unavailable']}; ok=False
        else: out=summarize_evaluation(ev)
    else:
        ev=HostRealEffectAdmissionRuntimeCoordinator().evaluate(closure_bundle_root=args.closure_bundle_root or '', output_root=args.output_root or '', correlation_id=args.correlation_id, admission_domain=args.admission_domain, requested_implementation_tier=args.requested_implementation_tier)
        out=ev.to_dict(); ok=validate_evaluation(ev).ok and not ev.status.startswith('blocked')
    text=json.dumps(out, sort_keys=True, indent=2)
    if args.output: Path(args.output).write_text(text, encoding='utf-8')
    else: print(text)
    return 0 if ok else 1
if __name__ == '__main__': raise SystemExit(main())
