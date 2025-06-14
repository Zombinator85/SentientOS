"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
from privilege_lint_cli import main as pl_main

def cli() -> None:
    ap = argparse.ArgumentParser(description="Run privilege linter")
    ap.add_argument("--mode", choices=["fix", "lint"], default="lint")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()
    argv = args.paths
    if args.mode == "fix":
        argv = ["--fix"] + argv
    rc = pl_main(argv)
    raise SystemExit(rc)

if __name__ == "__main__":
    cli()
