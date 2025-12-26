"""SentientOS package entrypoint."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    # Place type-only imports here in the future
    pass


SAFE_COMMANDS = {"status", "doctor", "ois"}


def _read_version() -> str:
    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    from . import __version__

    return __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentientos", description="SentientOS CLI entrypoint")
    parser.add_argument("--version", action="store_true", help="Show the SentientOS version and exit.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show read-only system status.")
    subparsers.add_parser("doctor", help="Run read-only diagnostics.")
    subparsers.add_parser("dashboard", help="Launch the SentientOS dashboard.")
    subparsers.add_parser("ois", help="Read-only Operator Introspection Surface (OIS).")
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


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for the SentientOS package."""

    argv = list(sys.argv[1:] if argv is None else argv)
    # Argument parsing occurs before privilege enforcement to allow safe introspection commands.
    parser = _build_parser()
    args, extra = parser.parse_known_args(argv)

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


if __name__ == "__main__":  # pragma: no cover - CLI invocation
    main()
