#!/usr/bin/env python3
"""Run privileged CI self checks."""
from __future__ import annotations
import os
import subprocess
import sys


FILES_TO_TYPECHECK = [
    "scripts/ritual_enforcer.py",
    "scripts/auto_approve.py",
    "audit_blesser.py",
    "memory_cli.py",
    "memory_tail.py",
]


def run_cmd(cmd: list[str], env: dict[str, str]) -> int:
    print("Running", " ".join(cmd))
    res = subprocess.run(cmd, env=env)
    return res.returncode


def main(argv: list[str] | None = None) -> int:
    env = os.environ.copy()
    env.setdefault("LUMOS_AUTO_APPROVE", "1")
    env.setdefault("PYTHONPATH", ".")
    steps = [
        ["python", "scripts/ritual_enforcer.py", "--mode", "check", "--files", "**/*.py"],
        ["mypy", "--strict", *FILES_TO_TYPECHECK],
        ["pytest", "-q"],
    ]
    for cmd in steps:
        code = run_cmd(cmd, env)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
