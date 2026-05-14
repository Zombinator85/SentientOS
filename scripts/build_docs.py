from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DOCS_DEPENDENCY_IMPORTS = ("mkdocs",)
DOCS_PIP_REQUIREMENTS = ("mkdocs>=1.6,<2", "watchdog>=2,<3")
DOCS_BOOTSTRAP_COMMAND = "python scripts/build_docs.py --bootstrap-docs"
DOCS_EXTRA_INSTALL_COMMAND = "pip install -e .[docs]"
DOCS_DEPENDENCY_MESSAGE = (
    "Docs build dependencies missing. Run: "
    f"{DOCS_BOOTSTRAP_COMMAND} (minimal), or {DOCS_EXTRA_INSTALL_COMMAND}"
)


def missing_docs_dependencies() -> list[str]:
    """Return docs build dependency imports unavailable in this environment."""

    return [name for name in DOCS_DEPENDENCY_IMPORTS if importlib.util.find_spec(name) is None]


def _emit_missing_dependency_message(missing: list[str]) -> None:
    joined = ", ".join(missing)
    print(
        "ENVIRONMENT/BOOTSTRAP ERROR: "
        f"{DOCS_DEPENDENCY_MESSAGE}\nMissing Python import(s): {joined}",
        file=sys.stderr,
    )


def bootstrap_docs_dependencies() -> bool:
    """Install only the minimal docs build toolchain for this environment."""

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", *DOCS_PIP_REQUIREMENTS],
        check=False,
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build documentation")
    parser.add_argument("--deploy", action="store_true", help="Deploy to GitHub Pages")
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="check docs build dependencies and mkdocs.yml without building",
    )
    parser.add_argument(
        "--bootstrap-docs",
        action="store_true",
        help="install the minimal docs dependency set before building",
    )
    args = parser.parse_args(argv)

    config = Path("mkdocs.yml")
    if not config.exists():
        print("mkdocs.yml not found", file=sys.stderr)
        return 1

    missing = missing_docs_dependencies()
    if missing and args.bootstrap_docs:
        if not bootstrap_docs_dependencies():
            print(
                "ENVIRONMENT/BOOTSTRAP ERROR: Docs dependency bootstrap failed. "
                f"Tried: pip install {' '.join(DOCS_PIP_REQUIREMENTS)}",
                file=sys.stderr,
            )
            return 2
        missing = missing_docs_dependencies()
    if missing:
        _emit_missing_dependency_message(missing)
        return 2
    if args.check_deps:
        print("Docs build dependencies available.")
        return 0

    cmd = [sys.executable, "-m", "mkdocs", "build", "--clean"]
    if args.deploy:
        cmd = [sys.executable, "-m", "mkdocs", "gh-deploy", "--force"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    if not args.deploy:
        site_dir = Path("site")
        pages = sorted(p.relative_to(site_dir) for p in site_dir.rglob("*.html"))
        print(f"Generated {len(pages)} pages:")
        for p in pages:
            print(f"- {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
