"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import sys

from privilege_lint_cli import main as pl_main


def _run_report(argv: list[str]) -> int:
    from privilege_lint.reporting.report_router import create_default_router

    ap = argparse.ArgumentParser(prog="privilege_lint report", description="Generate privilege lint report")
    ap.add_argument("--format", default="json", help="Report format (json|yaml|markdown)")
    ap.add_argument("paths", nargs="*", help="Optional paths to lint")
    args = ap.parse_args(argv)
    router = create_default_router()
    report, rendered, _, _ = router.generate(args.format, paths=args.paths or None)
    print(rendered)
    return 0 if report.passed else 1


def cli(argv: list[str] | None = None) -> None:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if argv and argv[0] == "report":
        rc = _run_report(argv[1:])
        raise SystemExit(rc)

    ap = argparse.ArgumentParser(description="Run privilege linter")
    ap.add_argument("--mode", choices=["fix", "lint"], default="lint")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args(argv)
    cli_args = args.paths
    if args.mode == "fix":
        cli_args = ["--fix"] + cli_args
    rc = pl_main(cli_args)
    raise SystemExit(rc)

if __name__ == "__main__":
    cli()
