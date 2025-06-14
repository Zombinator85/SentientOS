"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Build artifacts and publish package and Docker image.

On real runs this also generates ``sbom.json`` and ``docker_digests.txt``
which are attached to the GitHub release.
"""

import argparse
import os
import re
import subprocess
from pathlib import Path
from typing import Any


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    print(" ".join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def latest_changelog(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## ", text, flags=re.MULTILINE))
    if matches:
        start = matches[-1].start()
        return text[start:].strip()
    return text.strip()


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
        run([
            "cyclonedx-py",
            "requirements",
            "requirements.txt",
            "--output-format",
            "JSON",
            "-o",
            "sbom.json",
        ])
        with open("docker_digests.txt", "w", encoding="utf-8") as fh:
            run([
                "docker",
                "inspect",
                "--format={{index .RepoDigests 0}}",
                image,
            ], stdout=fh)
    else:
        print("Skipping docker push (--noop)")

    notes = latest_changelog(Path("docs/CHANGELOG.md"))
    Path("release_notes.txt").write_text(notes, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
