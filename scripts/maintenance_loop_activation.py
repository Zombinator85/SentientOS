#!/usr/bin/env python3
"""Operator CLI for local maintenance-loop activation."""
from __future__ import annotations
import argparse
import json
from typing import Sequence
from sentientos import maintenance_loop_activation as activation

def _emit(value: object) -> None: print(activation.canonical_bytes(value).decode())

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="activate the bounded maintenance loop without installing a scheduler")
    sub = parser.add_subparsers(dest="command", required=True)
    roots = sub.add_parser("init-roots"); roots.add_argument("--repository-root", required=True)
    for name in ("state", "workspace", "scratch", "inbox"): roots.add_argument("--" + name + "-root", required=True)
    render = sub.add_parser("render-config")
    for name in ("output", "repository-root", "state-root", "workspace-root", "scratch-root", "inbox-root", "standing-grant", "selector-policy", "foreman-policy", "validation-policy", "landing-policy", "base-sha", "tracked-base-ref"): render.add_argument("--" + name, required=True)
    render.add_argument("--implementation-backend", choices=("local_codex", "commissioned_local"), required=True)
    render.add_argument("--commissioned-local-activation")
    render.add_argument("--maximum-actions", type=int, required=True); render.add_argument("--maximum-wall-clock-seconds", type=int, required=True); render.add_argument("--publication-retry-backoff-seconds", type=int, required=True)
    for name in ("stop-marker", "control-journal", "base-cursor-journal"): render.add_argument("--" + name)
    for command in ("doctor-live", "smoke-idle", "print-run-command"):
        p = sub.add_parser(command); p.add_argument("--config", required=True); p.add_argument("--evaluation-time", required=True)
        if command == "doctor-live": p.add_argument("--probe-remote", action="store_true")
    inspect = sub.add_parser("inspect-activation"); inspect.add_argument("--receipts", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init-roots": out = activation.init_roots(args.repository_root, {k: getattr(args, k + "_root") for k in ("state", "workspace", "scratch", "inbox")})
        elif args.command == "render-config":
            names = ("output", "repository_root", "state_root", "workspace_root", "scratch_root", "inbox_root", "standing_grant", "selector_policy", "foreman_policy", "validation_policy", "landing_policy", "base_sha", "tracked_base_ref", "implementation_backend", "commissioned_local_activation", "maximum_actions", "maximum_wall_clock_seconds", "publication_retry_backoff_seconds", "stop_marker", "control_journal", "base_cursor_journal")
            out = activation.render_config(**{name: getattr(args, name) for name in names})
        elif args.command == "doctor-live": out = activation.doctor_live(args.config, evaluation_time=args.evaluation_time, probe_remote=args.probe_remote)
        elif args.command == "smoke-idle": out = activation.smoke_idle(args.config, evaluation_time=args.evaluation_time)
        elif args.command == "inspect-activation": out = activation.inspect_activation(args.receipts)
        else:
            av = activation.run_argv(args.config, args.evaluation_time); print(json.dumps(av, separators=(",", ":"))); print("Command: " + " ".join(json.dumps(x) for x in av)); return 0
        _emit(out); return 0 if out.get("status") not in {"activation_blocked", "activation_warning"} else 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        _emit({"schema_version": "sentientos.maintenance_activation_error:v1", "status": "activation_blocked", "reason": str(exc)}); return 2

if __name__ == "__main__": raise SystemExit(main())
