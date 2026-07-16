#!/usr/bin/env python3
# mypy: disable-error-code="no-untyped-def,no-untyped-call"
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

from sentientos.control_plane_kernel import LifecyclePhase, get_control_plane_kernel
from sentientos.host_resource_runtime import HostObservationBudget, HostResourceRuntimeCoordinator, build_observation_plan, default_collector_specs, persist_evidence_bundle, render_markdown, summary_for_evaluation, validate_evaluation, validate_epoch, validate_plan
from sentientos.world_state_board import to_dict


def _coord(args):
    root = Path(args.output_root or os.environ.get("SENTIENTOS_RUNTIME_STATE_ROOT", "/tmp/sentientos_host_resource_runtime"))
    kernel = get_control_plane_kernel(); kernel.set_phase(LifecyclePhase.MAINTENANCE, actor="build_host_resource_runtime")
    return HostResourceRuntimeCoordinator(kernel=kernel, runtime_state_root=root)

def _print(obj): print(json.dumps(obj, sort_keys=True, indent=2, default=str))

def main(argv=None):
    p=argparse.ArgumentParser(description="Inspect admitted read-only host resource runtime")
    p.add_argument("command", choices=["plan","collect","evaluate","validate-plan","validate-epoch","validate-bundle","summarize","list-collectors","inspect-collector","render-json","render-markdown","diff"])
    p.add_argument("--output-root")
    p.add_argument("--correlation-id", default="operator-host-resource-runtime")
    p.add_argument("--collector-id")
    p.add_argument("--input")
    p.add_argument("--before")
    p.add_argument("--after")
    args=p.parse_args(argv)
    plan=build_observation_plan()
    if args.command == "plan": _print(plan.to_dict()); return 0
    if args.command == "validate-plan": _print(validate_plan(plan).__dict__); return 0
    if args.command == "list-collectors": _print([c.to_dict() for c in default_collector_specs()]); return 0
    if args.command == "inspect-collector":
        for c in default_collector_specs():
            if c.collector_id == args.collector_id: _print(c.to_dict()); return 0
        print("unknown collector", file=sys.stderr); return 2
    if args.command == "diff":
        before=json.loads(Path(args.before).read_text()) if args.before else {}; after=json.loads(Path(args.after).read_text()) if args.after else {}; _print({"changed": before != after, "before_digest": hash(json.dumps(before, sort_keys=True)), "after_digest": hash(json.dumps(after, sort_keys=True))}); return 0
    c=_coord(args); ev=c.run_cycle(correlation_id=args.correlation_id)
    if ev is None: _print({"status":"not_allowed","collectors_called": c.collector_call_count}); return 1
    if args.command in {"collect","evaluate"}:
        receipt=c.persist_bundle(ev, tick_id=args.correlation_id); _print({"evaluation": ev.to_dict(), "receipt": receipt.to_dict()}); return 0
    if args.command == "validate-epoch": _print(validate_epoch(ev.epoch).__dict__); return 0
    if args.command == "validate-bundle": _print(validate_evaluation(ev).__dict__); return 0
    if args.command == "summarize": _print(summary_for_evaluation(ev)); return 0
    if args.command == "render-json": _print(ev.to_dict()); return 0
    if args.command == "render-markdown": print(render_markdown(ev)); return 0
    return 2
if __name__ == "__main__": raise SystemExit(main())
