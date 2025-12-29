from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents.forms.review_bundle import redact_dict, redact_log
from sentientos.consciousness.cognitive_state import (
    build_cognitive_state_snapshot,
    validate_cognitive_snapshot_version,
)
from sentientos.governance.intentional_forgetting import build_forget_pressure_snapshot
from sentientos.helpers import compute_system_diagnostics, load_profile_json
from sentientos.orchestrator import SentientOrchestrator


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _require_approval(approved: bool) -> None:
    if not approved:
        _print_json({"error": "approval_required"})
        sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentientos", description="SentientOS CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("cycle", help="Run a consciousness cycle")

    cognition_parser = subparsers.add_parser(
        "cognition", help="Cognitive state inspection commands"
    )
    cognition_subparsers = cognition_parser.add_subparsers(
        dest="cognition_command", required=True
    )
    cognition_status = cognition_subparsers.add_parser(
        "status", help="Show the unified cognitive state snapshot"
    )
    cognition_status.add_argument(
        "--expect-version",
        type=int,
        help="Assert the cognitive snapshot version matches the expected value",
    )

    ssa_parser = subparsers.add_parser("ssa", help="SSA agent commands")
    ssa_subparsers = ssa_parser.add_subparsers(dest="ssa_command", required=True)

    dry = ssa_subparsers.add_parser("dry-run", help="Run SSA dry-run plan")
    dry.add_argument("--profile", required=True, help="Path to SSA profile JSON")

    execute = ssa_subparsers.add_parser("execute", help="Execute SSA via OracleRelay")
    execute.add_argument("--profile", required=True, help="Path to SSA profile JSON")
    execute.add_argument("--approve", action="store_true", help="Allow privileged actions")

    prefill = ssa_subparsers.add_parser(
        "prefill-827", help="Prefill SSA-827 PDF with provided profile"
    )
    prefill.add_argument("--profile", required=True, help="Path to SSA profile JSON")
    prefill.add_argument("--approve", action="store_true", help="Allow PDF creation")

    review = ssa_subparsers.add_parser(
        "review", help="Summarize a previously generated review bundle"
    )
    review.add_argument("--bundle", required=True, help="Path to review bundle JSON")

    subparsers.add_parser("version", help="Print SentientOS version")
    subparsers.add_parser("integrity", help="Show deterministic integrity summary")

    return parser


def _load_bundle(path: str) -> dict:
    with open(Path(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _redacted_bundle_summary(bundle: dict) -> dict:
    execution_log = bundle.get("execution_log") if isinstance(bundle, dict) else None
    profile = bundle.get("profile") if isinstance(bundle, dict) else None

    return {
        "execution_log": redact_log(execution_log or []),
        "profile": redact_dict(profile or {}),
        "meta": {"pages": bundle.get("pages"), "status": bundle.get("status")},
    }


def _cognitive_status_snapshot() -> dict:
    pressure_snapshot = build_forget_pressure_snapshot()
    return build_cognitive_state_snapshot(pressure_snapshot=pressure_snapshot)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "cycle":
        orchestrator = SentientOrchestrator()
        _print_json(orchestrator.run_consciousness_cycle())
        return

    if args.command == "cognition":
        if args.cognition_command == "status":
            snapshot = _cognitive_status_snapshot()
            if args.expect_version is not None:
                try:
                    validate_cognitive_snapshot_version(
                        snapshot, expected_version=args.expect_version
                    )
                except (TypeError, ValueError) as exc:
                    _print_json({"error": str(exc)})
                    sys.exit(1)
            _print_json(snapshot)
            return

    if args.command == "version":
        version_path = Path("VERSION")
        if version_path.exists():
            _print_json({"version": version_path.read_text(encoding="utf-8").strip()})
        else:
            _print_json({"version": "unknown"})
        return

    if args.command == "integrity":
        _print_json(compute_system_diagnostics())
        return

    if args.command == "ssa":
        if args.ssa_command == "dry-run":
            profile = load_profile_json(args.profile)
            orchestrator = SentientOrchestrator(profile=profile)
            _print_json(orchestrator.ssa_dry_run())
            return

        if args.ssa_command == "execute":
            _require_approval(args.approve)
            profile = load_profile_json(args.profile)
            orchestrator = SentientOrchestrator(profile=profile, approval=args.approve)
            _print_json(orchestrator.ssa_execute(relay=None))
            return

        if args.ssa_command == "prefill-827":
            _require_approval(args.approve)
            profile = load_profile_json(args.profile)
            orchestrator = SentientOrchestrator(profile=profile, approval=args.approve)
            _print_json(orchestrator.ssa_prefill_827())
            return

        if args.ssa_command == "review":
            bundle = _load_bundle(args.bundle)
            _print_json(_redacted_bundle_summary(bundle))
            return


if __name__ == "__main__":
    main()
