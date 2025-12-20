"""SentientOS operations control CLI."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # pragma: no cover - runtime import guard
    from sentientos.autonomy import AutonomyRuntime, run_rehearsal
    from sentientos.perception.screen_ocr import ScreenOCR


def _cycles_from_duration(duration: str, profile: str) -> int:
    seconds = _parse_duration(duration)
    base = {"low": 2, "std": 4, "high": 6}
    per_block = base.get(profile, base["std"])
    blocks = max(1, int(seconds // 60) or 1)
    return per_block * blocks


def _parse_duration(value: str) -> float:
    text = value.strip().lower()
    if text.endswith("ms"):
        return max(1.0, float(text[:-2]) / 1000.0)
    if text.endswith("s"):
        return max(1.0, float(text[:-1]))
    if text.endswith("m"):
        return max(60.0, float(text[:-1]) * 60.0)
    return max(60.0, float(text))


def _service_action(action: str, *, unit_override: str | None = None) -> dict[str, object]:
    dry_run = os.getenv("SENTIENTOS_SERVICE_DRY_RUN", "0").lower() in {"1", "true", "yes"}
    if dry_run:
        has_yaml = False
    else:
        try:  # optional dependency for YAML-based service rendering
            import yaml  # type: ignore[import-not-found]

            has_yaml = True
        except ImportError:
            has_yaml = False

    override = os.getenv("SENTIENTOS_SERVICE_PLATFORM")
    system = override.lower() if override else platform.system().lower()
    notices: list[dict[str, str]] = []
    commands: list[list[str]] = []
    rendering_required = action == "install"
    if system.startswith("win"):
        script = Path(__file__).parent / "packaging" / "windows" / "sentientos_windows_service.ps1"
        command = ["powershell.exe", "-File", str(script), "-Action", action]
        if unit_override:
            command.extend(["-ServiceName", unit_override])
        commands.append(command)
    else:
        unit_path = unit_override or str(Path(__file__).parent / "packaging" / "systemd" / "sentientos.service")
        if action == "install":
            commands.append(["systemctl", "link", unit_path])
            commands.append(["systemctl", "enable", "--now", "sentientos.service"])
        else:
            commands.append(["systemctl", action, "sentientos.service"])

    if rendering_required and not has_yaml:
        notice = {
            "dependency": "PyYAML",
            "effect": "service rendering skipped",
            "mode": "dry-run" if dry_run else "required",
        }
        if dry_run:
            notices.append(notice)
        else:
            raise RuntimeError("PyYAML is required to render service configuration; install it or use --dry-run")
    executed: list[list[str]] = []
    for command in commands:
        executed.append(command)
        if dry_run:
            continue
        subprocess.run(command, check=True)
    return {
        "action": action,
        "commands": executed,
        "dry_run": dry_run,
        "notices": notices,
        "system": system,
        "yaml_available": has_yaml,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sosctl", description="SentientOS autonomy control")
    sub = parser.add_subparsers(dest="command")

    rehearse = sub.add_parser("rehearse", help="Execute autonomy rehearsal")
    rehearse.add_argument("--cycles", type=int, default=1, help="Number of rehearsal cycles")
    rehearse.add_argument("--duration", default=None, help="Desired rehearsal duration (e.g. 10m)")
    rehearse.add_argument(
        "--load-profile",
        choices=["low", "std", "high"],
        default="std",
        help="Synthetic workload profile",
    )

    goals = sub.add_parser("goals", help="Goal curator helpers")
    goals_sub = goals.add_subparsers(dest="goals_command")
    enqueue = goals_sub.add_parser("enqueue", help="Enqueue an autonomous goal")
    enqueue.add_argument("--title", required=True)
    enqueue.add_argument("--support", type=int, default=1)
    enqueue.add_argument("--ttl", default="3d")

    council = sub.add_parser("council", help="Council operations")
    council_sub = council.add_subparsers(dest="council_command")
    vote = council_sub.add_parser("vote", help="Record a council vote")
    vote.add_argument("--amendment", required=True)
    vote.add_argument("--for", dest="votes_for", type=int, default=1)
    vote.add_argument("--against", dest="votes_against", type=int, default=0)

    reflexion = sub.add_parser("reflexion", help="Manage reflexion notes")
    reflexion_sub = reflexion.add_subparsers(dest="reflexion_command")
    run_reflexion = reflexion_sub.add_parser("run", help="Record a reflexion note")
    run_reflexion.add_argument("--since", default="1d")

    hungry = sub.add_parser("hungry-eyes", help="HungryEyes operations")
    hungry_sub = hungry.add_subparsers(dest="hungry_command")
    hungry_sub.add_parser("retrain", help="Force a HungryEyes retrain")

    metrics = sub.add_parser("metrics", help="Metrics utilities")
    metrics_sub = metrics.add_subparsers(dest="metrics_command")
    metrics_sub.add_parser("snapshot", help="Persist a metrics snapshot")

    service = sub.add_parser("service", help="Manage SentientOS background service")
    service.add_argument("action", choices=["install", "start", "stop", "status"])
    service.add_argument("--unit", help="Optional override for service unit path")

    say = sub.add_parser("say", help="Speak via the configured TTS backend")
    say.add_argument("text", help="Text to speak")

    asr = sub.add_parser("asr-smoke", help="Emit a synthetic ASR observation")
    asr.add_argument("--amplitude", type=float, default=0.1)
    asr.add_argument("--seconds", type=float, default=1.0)

    screen = sub.add_parser("screen-ocr-smoke", help="Run a synthetic screen OCR capture")
    screen.add_argument("--text", required=True, help="Text to inject into the OCR pipeline")
    screen.add_argument("--title", default="smoke", help="Window title")

    social = sub.add_parser("social-smoke", help="Dry-run browser automation")
    social.add_argument("URL", help="URL to open")
    social.add_argument("--action", choices=["open", "click", "type"], default="open")
    social.add_argument("--selector", help="CSS selector for click/type actions")
    social.add_argument("--text", help="Text for type actions", default="")

    return parser


def handle(args: argparse.Namespace) -> int:
    if args.command == "service":
        response = _service_action(args.action, unit_override=args.unit)
        print(json.dumps(response, indent=2))
        return 0

    from sentientos.autonomy import AutonomyRuntime, run_rehearsal
    from sentientos.config import load_runtime_config

    runtime = AutonomyRuntime.from_config(load_runtime_config())

    if args.command == "rehearse":
        cycles = args.cycles
        if args.duration:
            cycles = max(cycles, _cycles_from_duration(args.duration, args.load_profile))
        result = run_rehearsal(cycles=cycles, runtime=runtime)
        payload = result["report"].copy()
        payload["cycles"] = cycles
        payload["load_profile"] = args.load_profile
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "goals" and args.goals_command == "enqueue":
        created = runtime.goal_curator.consider(
            {"title": args.title, "ttl": args.ttl},
            corr_id="cli",
            support_count=args.support,
        )
        status = runtime.goal_curator.status()
        active = status.get("active", 0)
        print(json.dumps({"created": created, "active": active}))
        return 0
    if args.command == "council" and args.council_command == "vote":
        decision = runtime.council.vote(
            args.amendment,
            corr_id="cli",
            votes_for=args.votes_for,
            votes_against=args.votes_against,
        )
        print(json.dumps({
            "outcome": decision.outcome.value,
            "quorum_met": decision.quorum_met,
            "votes_for": decision.votes_for,
            "votes_against": decision.votes_against,
        }))
        return 0
    if args.command == "reflexion" and args.reflexion_command == "run":
        note = runtime.reflexion.run(f"Reflexion since {args.since}", corr_id="cli")
        print(json.dumps({"note": note}))
        return 0
    if args.command == "hungry-eyes" and args.hungry_command == "retrain":
        payload = {"status": "VALID", "support": 1}
        report = runtime.hungry_eyes.observe(payload)
        print(json.dumps(report))
        return 0
    if args.command == "metrics" and args.metrics_command == "snapshot":
        runtime.metrics.persist_snapshot()
        runtime.metrics.persist_prometheus()
        print(json.dumps({"status": "ok"}))
        return 0
    if args.command == "say":
        runtime.tts._config.enable = True
        runtime.tts.enqueue(args.text, corr_id="cli")
        spoken = runtime.tts.drain()
        print(json.dumps({"spoken": spoken}))
        return 0
    if args.command == "asr-smoke":
        runtime.asr._config.enable = True
        samples = [float(args.amplitude)] * int(max(1.0, args.seconds) * 16000)
        observation = runtime.asr.process_samples(samples, sample_rate=16000)
        print(json.dumps(observation or {}))
        return 0
    if args.command == "screen-ocr-smoke":
        from sentientos.perception.screen_ocr import ScreenOCR

        runtime.config.screen.enable = True
        runtime.screen = ScreenOCR(
            runtime.config.screen,
            capture_fn=lambda: {"data": args.text, "title": args.title},
            metrics=runtime.metrics,
        )
        observation = runtime.screen.snapshot()
        print(json.dumps(observation or {}))
        return 0
    if args.command == "social-smoke":
        try:
            runtime.social._config.enable = True
            domain = args.URL.split("/")[2] if "//" in args.URL else args.URL
            allow = tuple(runtime.social._config.domains_allowlist) or (domain,)
            if domain not in allow:
                allow = allow + (domain,)
            runtime.social._config.domains_allowlist = allow
            if args.action == "open":
                runtime.social.open_url(args.URL)
            elif args.action == "click" and args.selector:
                runtime.social.click(args.selector)
            elif args.action == "type" and args.selector:
                runtime.social.type_text(args.selector, args.text)
            else:
                raise ValueError("selector required for this action")
        except Exception as exc:
            print(json.dumps({"error": str(exc)}))
            return 1
        print(json.dumps(runtime.social.status()))
        return 0
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    return handle(args)


if __name__ == "__main__":
    sys.exit(main())
