"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Lock management helper.

Usage:
  python -m scripts.lock freeze   # regenerate lock files and hash markers
  python -m scripts.lock install  # install from requirements-lock.txt then package
  python -m scripts.lock check    # fail if lock hashes drift
"""

import hashlib
import pathlib
import subprocess
import sys
import textwrap

LOCKS = (
    "requirements-lock.txt",
    "requirements-src-lock.txt",
)


def _hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _pip_compile(lock: str, pip_args: str = "") -> None:
    cmd = [
        "pip-compile",
        "--generate-hashes",
        "--no-annotate",
        "requirements.txt",
        "-o",
        lock,
    ]
    if pip_args:
        cmd.extend(["--pip-args", pip_args])
    subprocess.check_call(cmd)


def freeze() -> None:
    for lock, args in zip(LOCKS, ("", "--no-binary :all:")):
        print(f"[lock] regenerating {lock}")
        _pip_compile(lock, args)
        h = _hash(pathlib.Path(lock))
        pathlib.Path(lock + ".sha").write_text(h + "\n")


def install() -> None:
    for lock in LOCKS:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", lock])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "."])


def check() -> None:
    bad: list[str] = []
    for lock in LOCKS:
        path = pathlib.Path(lock)
        want = pathlib.Path(lock + ".sha")
        if not path.exists() or not want.exists():
            bad.append(lock)
            continue
        real = _hash(path)
        if real != want.read_text().strip():
            bad.append(lock)
    if bad:
        print("\U0001f512 lock drift detected:", *bad)
        sys.exit(1)


def cli() -> None:
    usage = textwrap.dedent(
        """\
        usage: python -m scripts.lock [freeze|install|check]
          freeze  – regenerate lock files & .sha markers
          install – pip install -r requirements-lock.txt
          check   – exit-1 if lock hashes drift
        """
    )
    if len(sys.argv) != 2 or sys.argv[1] not in {"freeze", "install", "check"}:
        print(usage, file=sys.stderr)
        sys.exit(2)
    {"freeze": freeze, "install": install, "check": check}[sys.argv[1]]()


if __name__ == "__main__":
    cli()
