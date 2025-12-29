"""SentientOS package entrypoint."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from sentientos.diagnostics import (
    DiagnosticErrorFrame,
    FailedPhase,
    RecoveryEligibility,
    RecoveryOutcome,
    attempt_recovery,
    format_recovery_eligibility,
    frame_exception,
    persist_error_frame,
    persist_recovery_proof,
)

if TYPE_CHECKING:
    # Place type-only imports here in the future
    pass


SAFE_COMMANDS = {"status", "doctor", "ois", "diff", "summary"}


def _read_version() -> str:
    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    from . import __version__

    return __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentientos", description="SentientOS CLI entrypoint")
    parser.add_argument("--version", action="store_true", help="Show the SentientOS version and exit.")
    parser.add_argument("--explain", action="store_true", help="Show full diagnostic error details.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable diagnostic JSON.")
    parser.add_argument("--trace", action="store_true", help="Show raw traceback for failures.")
    parser.add_argument("--no-recover", action="store_true", help="Disable automatic recovery ladders.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show read-only system status.")
    subparsers.add_parser("doctor", help="Run read-only diagnostics.")
    subparsers.add_parser("dashboard", help="Launch the SentientOS dashboard.")
    subparsers.add_parser("diff", help="Show authority surface changes (read-only).")
    subparsers.add_parser("ois", help="Read-only Operator Introspection Surface (OIS).")
    subparsers.add_parser("summary", help="Show narrative system summaries (read-only).")
    subparsers.add_parser("avatar-demo", help="Run the avatar demo.")
    return parser


def _enforce_privileges() -> None:
    from sentientos.privilege import require_admin_banner, require_lumos_approval

    require_admin_banner()
    require_lumos_approval()


def _print_status() -> None:
    print("Status: locked for privileged operations. Use --help for safe commands.")


def _print_doctor() -> None:
    from sentientos.helpers import compute_system_diagnostics

    print("Doctor: read-only diagnostics available. No privileged checks were performed.")
    report = compute_system_diagnostics()
    print(json.dumps(report, indent=2, sort_keys=True))


def _emit_error(frame, args) -> None:
    if args.json:
        print(frame.to_json())
        return
    if args.explain:
        print(frame.to_json(indent=2))
        return
    print(frame.human_summary)
    print(f"error_code: {frame.error_code}")
    print(f"failed_phase: {frame.failed_phase.value}")
    print(format_recovery_eligibility(frame.recovery_eligibility))


def _emit_optional_dependency_notice(*, capability: str, module: str) -> None:
    print(f"Optional capability ‹{capability}› disabled due to missing dependency ‹{module}›.")
    print(f"Install ‹{module}› to re-enable ‹{capability}›.")


def _maybe_attempt_recovery(frame: DiagnosticErrorFrame, args) -> RecoveryOutcome | None:
    if getattr(args, "no_recover", False):
        return None
    if frame.recovery_eligibility != RecoveryEligibility.RECOVERABLE:
        return None
    return attempt_recovery(frame)


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for the SentientOS package."""

    argv = list(sys.argv[1:] if argv is None else argv)
    # Argument parsing occurs before privilege enforcement to allow safe introspection commands.
    parser = _build_parser()
    args, extra = parser.parse_known_args(argv)

    try:
        if args.command is None and extra:
            parser.parse_args(argv)
            return

        if args.version:
            print(f"SentientOS {_read_version()}")
            return

        if args.command in SAFE_COMMANDS:
            if extra:
                parser.parse_args(argv)
                return
            if args.command == "status":
                _print_status()
                return
            if args.command == "ois":
                from sentientos.cli.ois_cli import main as ois_main

                raise SystemExit(ois_main(extra))
            if args.command == "diff":
                from sentientos.cli.authority_diff_cli import main as diff_main

                raise SystemExit(diff_main(extra))
            if args.command == "summary":
                from sentientos.cli.summary_cli import main as summary_main

                raise SystemExit(summary_main(extra))
            _print_doctor()
            return

        if args.command in {"dashboard", "avatar-demo"}:
            _enforce_privileges()
            if args.command == "dashboard":
                from sentientos.cli.dashboard_cli import main as dashboard_main

                raise SystemExit(dashboard_main(extra))
            from sentientos.cli.avatar_demo_cli import main as avatar_demo_main

            raise SystemExit(avatar_demo_main(extra))

        print(f"SentientOS {_read_version()}\nRun 'support' or 'ritual' for CLI tools.")
    except Exception as exc:
        if args.trace:
            raise
        frame = frame_exception(
            exc,
            failed_phase=FailedPhase.CLI,
            suppressed_actions=["auto_recovery", "retry", "state_mutation"],
        )
        persist_error_frame(frame)
        outcome = _maybe_attempt_recovery(frame, args)
        if outcome is not None and outcome.status == "RECOVERY_SUCCEEDED":
            if outcome.proof is not None:
                persist_recovery_proof(outcome.proof)
                if outcome.proof.disabled_capability and outcome.proof.missing_module:
                    _emit_optional_dependency_notice(
                        capability=outcome.proof.disabled_capability,
                        module=outcome.proof.missing_module,
                    )
                print("No further automatic recovery will be attempted for this error.")
            if outcome.recovered_frame is not None:
                persist_error_frame(outcome.recovered_frame)
            raise SystemExit(0) from exc
        _emit_error(frame, args)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # pragma: no cover - CLI invocation
    main()
