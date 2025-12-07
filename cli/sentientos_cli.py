from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents.forms.review_bundle import redact_dict, redact_log
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


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "cycle":
        orchestrator = SentientOrchestrator()
        _print_json(orchestrator.run_consciousness_cycle())
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
