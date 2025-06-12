from __future__ import annotations
"""Publish package and Docker image to test registries."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import argparse
import os
import re
import subprocess
from pathlib import Path


def latest_changelog(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## ", text, flags=re.MULTILINE))
    if matches:
        start = matches[-1].start()
        return text[start:].strip()
    return text.strip()


def run(cmd: list[str]) -> None:
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build and publish release")
    ap.add_argument("--noop", action="store_true", help="dry run")
    ap.add_argument("--tag", required=True, help="image tag")
    args = ap.parse_args(argv)

    run(["python", "-m", "build", "--wheel"])

    twine_cmd = [
        "twine",
        "upload",
        "--repository",
        "testpypi",
        "-u",
        "__token__",
        "-p",
        os.environ.get("TEST_PYPI_TOKEN", ""),
        "dist/*",
    ]
    if args.noop:
        twine_cmd.insert(1, "--dry-run")
    run(twine_cmd)

    image = f"ghcr.io/{os.environ.get('GITHUB_REPOSITORY', '')}:{args.tag}"
    run(["docker", "build", "-t", image, "."])
    if not args.noop:
        run([
            "docker",
            "login",
            "ghcr.io",
            "-u",
            os.environ.get("GITHUB_ACTOR", ""),
            "-p",
            os.environ.get("GHCR_PAT", ""),
        ])
        run(["docker", "push", image])
    else:
        print("Skipping docker push (--noop)")

    notes = latest_changelog(Path("docs/CHANGELOG.md"))
    Path("release_notes.txt").write_text(notes, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
