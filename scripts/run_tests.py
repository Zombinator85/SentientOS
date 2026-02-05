from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from scripts.editable_install import editable_install_from_repo_root

REPO_ROOT = Path(__file__).resolve().parents[1]
PRECHECK_MESSAGE = (
    "Not running against an editable install of this repo. "
    "Run pip install -e .[dev] or python -m scripts.run_tests."
)


def _imports_ok() -> bool:
    proc = subprocess.run(
        [sys.executable, "-c", "import fastapi, sentientos"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _install_deps() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
        cwd=REPO_ROOT,
        check=False,
    )
    return proc.returncode == 0


def _emit_run_context(
    install_performed: bool,
    pytest_args: list[str],
    *,
    editable_ok: bool,
    repo_root: Path,
    bypass_env: str | None,
) -> None:
    joined_args = " ".join(pytest_args) if pytest_args else "(none)"
    context = [
        f"python={sys.executable}",
        f"install_performed={install_performed}",
        f"editable_ok={str(editable_ok).lower()}",
        f"repo_root={repo_root}",
        f"pytest_args={joined_args}",
    ]
    if bypass_env:
        context.append("bypass_env=SENTIENTOS_ALLOW_NAKED_PYTEST=1")
    print(
        "run_tests: " + " ".join(context)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install SentientOS dev deps (if needed) and run pytest.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to pytest.",
    )
    args = parser.parse_args(argv)

    bypass_env = os.getenv("SENTIENTOS_ALLOW_NAKED_PYTEST")
    install_performed = False
    editable_ok = editable_install_from_repo_root(REPO_ROOT)
    if not editable_ok:
        install_performed = True
        if not _install_deps():
            _emit_run_context(
                install_performed,
                args.pytest_args,
                editable_ok=editable_ok,
                repo_root=REPO_ROOT,
                bypass_env=bypass_env,
            )
            print(PRECHECK_MESSAGE)
            return 1

    editable_ok = editable_install_from_repo_root(REPO_ROOT)
    imports_ok = _imports_ok()
    if not editable_ok or not imports_ok:
        _emit_run_context(
            install_performed,
            args.pytest_args,
            editable_ok=editable_ok,
            repo_root=REPO_ROOT,
            bypass_env=bypass_env,
        )
        print(PRECHECK_MESSAGE)
        return 1

    _emit_run_context(
        install_performed,
        args.pytest_args,
        editable_ok=editable_ok,
        repo_root=REPO_ROOT,
        bypass_env=bypass_env,
    )
    cmd = [sys.executable, "-m", "pytest"]
    if args.pytest_args:
        cmd.extend(args.pytest_args)
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
