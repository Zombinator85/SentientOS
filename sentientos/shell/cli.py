"""Command line harness for interacting with the SentientOS shell."""

from __future__ import annotations
"""Command line harness for interacting with the SentientOS shell."""

import argparse
import json
import os
from pathlib import Path

from . import SentientShell, ShellEventLogger
from sentientos.diagnostics import (
    FailedPhase,
    format_recovery_eligibility,
    frame_exception,
    persist_error_frame,
)


def _default_ci_runner() -> bool:
    return True


def _build_shell() -> SentientShell:
    run_ci = os.getenv("SENTIENT_SHELL_RUN_CI", "0").lower() in {"1", "true", "yes"}
    ci_runner = None if run_ci else _default_ci_runner
    logger = ShellEventLogger(pulse_source="ShellCLI")
    return SentientShell(logger=logger, ci_runner=ci_runner)


def _handle_start_menu(shell: SentientShell, args: argparse.Namespace) -> int:
    if args.list:
        for name in shell.start_menu.list_applications():
            print(name)
        return 0
    if args.search:
        results = shell.search(args.search)
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    if args.launch:
        result = shell.launch(args.launch)
        print(json.dumps({"launched": args.launch, "result": str(result)}))
        return 0
    pinned = shell.start_menu.list_pinned()
    print(json.dumps({"pinned": pinned}, indent=2))
    return 0


def _handle_install(shell: SentientShell, args: argparse.Namespace) -> int:
    package = Path(args.path)
    try:
        if args.method == "double-click":
            result = shell.install_via_double_click(package)
        elif args.method == "drag":
            result = shell.install_via_drag_and_drop(package)
        else:
            result = shell.install_from_button(package)
    except Exception as exc:  # pragma: no cover - CLI surface
        if getattr(args, "trace", False):
            raise
        frame = frame_exception(
            exc,
            failed_phase=FailedPhase.INSTALL,
            suppressed_actions=["auto_recovery", "retry", "state_mutation"],
            technical_details={"package": package.as_posix(), "method": args.method},
        )
        _emit_error(frame, args)
        persist_error_frame(frame)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SentientOS shell harness")
    parser.add_argument("--explain", action="store_true", help="Show full diagnostic error details.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable diagnostic JSON.")
    parser.add_argument("--trace", action="store_true", help="Show raw traceback for failures.")
    subparsers = parser.add_subparsers(dest="command")

    start_menu = subparsers.add_parser("start-menu", help="Inspect the start menu")
    start_menu.add_argument("--list", action="store_true", help="List all registered applications")
    start_menu.add_argument("--search", help="Search for applications or settings")
    start_menu.add_argument("--launch", help="Launch an application by name")

    install = subparsers.add_parser("install", help="Install a desktop application")
    install.add_argument("path", help="Path to a .deb or .AppImage package")
    install.add_argument(
        "--method",
        choices=["button", "double-click", "drag"],
        default="button",
        help="Installation trigger to simulate",
    )

    return parser


def _emit_error(frame, args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        print(frame.to_json())
        return
    if getattr(args, "explain", False):
        print(frame.to_json(indent=2))
        return
    print(frame.human_summary)
    print(f"error_code: {frame.error_code}")
    print(f"failed_phase: {frame.failed_phase.value}")
    print(format_recovery_eligibility(frame.recovery_eligibility))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    shell = _build_shell()
    if args.command == "start-menu":
        return _handle_start_menu(shell, args)
    if args.command == "install":
        return _handle_install(shell, args)
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
