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
    scheduler_render = sub.add_parser("render-scheduler-config")
    for name in ("output", "watchdog-config-path", "scheduler-state-root", "initial-run-posture", "schedule-anchor-utc"):
        scheduler_render.add_argument("--" + name, required=True)
    for name in ("cadence-interval-seconds", "maximum-cycles", "maximum-scheduler-wall-clock-seconds", "consecutive-failure-threshold"):
        scheduler_render.add_argument("--" + name, required=True, type=int)
    scheduler_doctor = sub.add_parser("doctor-scheduler"); scheduler_doctor.add_argument("--config", required=True)
    scheduler_command = sub.add_parser("print-scheduler-command"); scheduler_command.add_argument("--config", required=True)
    daemon_adoption = sub.add_parser("render-daemon-adoption")
    daemon_adoption.add_argument("--output", required=True); daemon_adoption.add_argument("--scheduler-config-path", required=True)
    daemon_adoption.add_argument("--evidence-path", required=True); daemon_adoption.add_argument("--enabled", action="store_true")
    daemon_adoption.add_argument("--shutdown-timeout-seconds", type=float, required=True)
    daemon_adoption.add_argument("--reentry-delay-seconds", type=float, required=True)
    wake_adoption = sub.add_parser("render-wake-daemon-adoption")
    for name in ("output", "wake-config-path", "cadence-state-root", "schedule-anchor-utc", "initial-run-posture"):
        wake_adoption.add_argument("--" + name, required=True)
    wake_adoption.add_argument("--enabled", action="store_true")
    for name in ("cadence-interval-seconds", "maximum-cycles", "maximum-daemon-wall-clock-seconds"):
        wake_adoption.add_argument("--" + name, required=True, type=int)
    wake_adoption.add_argument("--shutdown-timeout-seconds", required=True, type=float)
    args = parser.parse_args(argv)
    try:
        if args.command == "init-roots": out = activation.init_roots(args.repository_root, {k: getattr(args, k + "_root") for k in ("state", "workspace", "scratch", "inbox")})
        elif args.command == "render-config":
            names = ("output", "repository_root", "state_root", "workspace_root", "scratch_root", "inbox_root", "standing_grant", "selector_policy", "foreman_policy", "validation_policy", "landing_policy", "base_sha", "tracked_base_ref", "implementation_backend", "commissioned_local_activation", "maximum_actions", "maximum_wall_clock_seconds", "publication_retry_backoff_seconds", "stop_marker", "control_journal", "base_cursor_journal")
            out = activation.render_config(**{name: getattr(args, name) for name in names})
        elif args.command == "doctor-live": out = activation.doctor_live(args.config, evaluation_time=args.evaluation_time, probe_remote=args.probe_remote)
        elif args.command == "smoke-idle": out = activation.smoke_idle(args.config, evaluation_time=args.evaluation_time)
        elif args.command == "inspect-activation": out = activation.inspect_activation(args.receipts)
        elif args.command == "render-scheduler-config":
            scheduler_names = ("output", "watchdog_config_path", "scheduler_state_root", "cadence_interval_seconds", "initial_run_posture", "schedule_anchor_utc", "maximum_cycles", "maximum_scheduler_wall_clock_seconds", "consecutive_failure_threshold")
            out = activation.render_scheduler_config(**{name: getattr(args, name) for name in scheduler_names})
        elif args.command == "doctor-scheduler":
            from sentientos import maintenance_loop_scheduler as scheduler
            out = scheduler.doctor(scheduler.load_config(args.config))
        elif args.command == "render-daemon-adoption":
            out = activation.render_daemon_adoption(args.output, scheduler_config_path=args.scheduler_config_path,
                evidence_path=args.evidence_path, enabled=args.enabled,
                shutdown_timeout_seconds=args.shutdown_timeout_seconds, reentry_delay_seconds=args.reentry_delay_seconds)
        elif args.command == "render-wake-daemon-adoption":
            wake_names = ("output", "wake_config_path", "cadence_state_root", "enabled", "cadence_interval_seconds",
                     "schedule_anchor_utc", "initial_run_posture", "maximum_cycles",
                     "maximum_daemon_wall_clock_seconds", "shutdown_timeout_seconds")
            out = activation.render_wake_daemon_adoption(**{name: getattr(args, name) for name in wake_names})
        elif args.command == "print-scheduler-command":
            av = activation.scheduler_argv(args.config); print(json.dumps(av, separators=(",", ":"))); print("Command: " + " ".join(json.dumps(x) for x in av)); return 0
        else:
            av = activation.run_argv(args.config, args.evaluation_time); print(json.dumps(av, separators=(",", ":"))); print("Command: " + " ".join(json.dumps(x) for x in av)); return 0
        _emit(out); return 0 if out.get("status") not in {"activation_blocked", "activation_warning"} else 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        _emit({"schema_version": "sentientos.maintenance_activation_error:v1", "status": "activation_blocked", "reason": str(exc)}); return 2

if __name__ == "__main__": raise SystemExit(main())
