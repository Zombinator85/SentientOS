from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build documentation")
    parser.add_argument("--deploy", action="store_true", help="Deploy to GitHub Pages")
    args = parser.parse_args(argv)

    config = Path("mkdocs.yml")
    if not config.exists():
        print("mkdocs.yml not found", file=sys.stderr)
        return 1

    cmd = ["mkdocs", "build", "--clean"]
    if args.deploy:
        cmd = ["mkdocs", "gh-deploy", "--force"]
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
