from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from scripts.editable_install import EditableInstallStatus, get_editable_install_status

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


def _git_sha(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and sha else "unknown"


def _write_provenance(
    *,
    repo_root: Path,
    install_performed: bool,
    pytest_args: list[str],
    editable_status: EditableInstallStatus,
    bypass_env: bool,
    exit_reason: str | None,
) -> None:
    run_dir = repo_root / "glow" / "test_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    reason = editable_status.reason
    if bypass_env:
        reason = f"{reason}+bypass-env"
    payload: dict[str, object] = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.executable,
        "repo_root": str(repo_root),
        "git_sha": _git_sha(repo_root),
        "editable_ok": editable_status.ok,
        "editable_reason": reason,
        "bypass_env": bypass_env,
        "install_performed": install_performed,
        "pytest_args": list(pytest_args),
    }
    if exit_reason:
        payload["exit_reason"] = exit_reason
    target = run_dir / "test_run_provenance.json"
    with NamedTemporaryFile("w", delete=False, dir=run_dir, encoding="utf-8") as temp_file:
        json.dump(payload, temp_file, indent=2, sort_keys=True)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.replace(target)


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

    bypass_env = os.getenv("SENTIENTOS_ALLOW_NAKED_PYTEST") == "1"
    install_performed = False
    editable_status = get_editable_install_status(REPO_ROOT)
    if not editable_status.ok:
        install_performed = True
        if not _install_deps():
            _write_provenance(
                repo_root=REPO_ROOT,
                install_performed=install_performed,
                pytest_args=args.pytest_args,
                editable_status=editable_status,
                bypass_env=bypass_env,
                exit_reason="install-failed",
            )
            _emit_run_context(
                install_performed,
                args.pytest_args,
                editable_ok=editable_status.ok,
                repo_root=REPO_ROOT,
                bypass_env="1" if bypass_env else None,
            )
            print(PRECHECK_MESSAGE)
            return 1

    editable_status = get_editable_install_status(REPO_ROOT)
    imports_ok = _imports_ok()
    if not editable_status.ok or not imports_ok:
        _write_provenance(
            repo_root=REPO_ROOT,
            install_performed=install_performed,
            pytest_args=args.pytest_args,
            editable_status=editable_status,
            bypass_env=bypass_env,
            exit_reason="airlock-failed",
        )
        _emit_run_context(
            install_performed,
            args.pytest_args,
            editable_ok=editable_status.ok,
            repo_root=REPO_ROOT,
            bypass_env="1" if bypass_env else None,
        )
        print(PRECHECK_MESSAGE)
        return 1

    _write_provenance(
        repo_root=REPO_ROOT,
        install_performed=install_performed,
        pytest_args=args.pytest_args,
        editable_status=editable_status,
        bypass_env=bypass_env,
        exit_reason=None,
    )
    _emit_run_context(
        install_performed,
        args.pytest_args,
        editable_ok=editable_status.ok,
        repo_root=REPO_ROOT,
        bypass_env="1" if bypass_env else None,
    )
    cmd = [sys.executable, "-m", "pytest"]
    if args.pytest_args:
        cmd.extend(args.pytest_args)
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
