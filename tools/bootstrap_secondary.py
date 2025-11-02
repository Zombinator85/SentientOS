#!/usr/bin/env python3
"""Validate that the vendored secondary build tree is present.

The CI and devcontainer workflows rely on the checked-in copy of
``SentientOSsecondary/llama.cpp``.  This script performs a lightweight
validation so the build fails fast with a useful error message when the
vendor tree is missing or incomplete.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SECONDARY_ROOT = REPO_ROOT / "SentientOSsecondary"
LLAMA_ROOT = SECONDARY_ROOT / "llama.cpp"


def _expected_paths() -> list[Path]:
    server_root = LLAMA_ROOT / "examples" / "server"
    return [
        server_root / "CMakeLists.txt",
        server_root / "server.cpp",
        server_root / "embed_asset.cmake",
        server_root / "generate_static_asset_manifest.cmake",
        server_root / "public" / "app.js",
        server_root / "public" / "index.html",
        server_root / "public" / "index.js",
    ]


def validate_secondary(verbose: bool) -> None:
    if not SECONDARY_ROOT.exists():
        raise SystemExit(
            "SentientOSsecondary/ is missing. The vendor tree must be committed to the repo."
        )

    if not LLAMA_ROOT.exists():
        raise SystemExit(
            "SentientOSsecondary/llama.cpp is missing. Restore it from git history "
            "or fetch the pinned source before running the build."
        )

    missing = [path for path in _expected_paths() if not path.exists()]
    if missing:
        formatted = "\n".join(f"- {path.relative_to(REPO_ROOT)}" for path in missing)
        raise SystemExit(
            "The vendored llama.cpp tree is incomplete. Missing files:\n" + formatted
        )

    if verbose:
        print("SentientOSsecondary vendor tree located:")
        print(f"- root: {SECONDARY_ROOT.relative_to(REPO_ROOT)}")
        print(f"- llama.cpp: {LLAMA_ROOT.relative_to(REPO_ROOT)}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet", action="store_true", help="suppress status output when validation succeeds"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    validate_secondary(verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
