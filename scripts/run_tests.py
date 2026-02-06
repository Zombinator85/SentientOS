from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from scripts.editable_install import EditableInstallStatus, get_editable_install_status

REPO_ROOT = Path(__file__).resolve().parents[1]
PRECHECK_MESSAGE = (
    "Not running against an editable install of this repo. "
    "Run pip install -e .[dev] or python -m scripts.run_tests."
)
BYPASS_ENV_VARS = (
    "SENTIENTOS_ALLOW_NAKED_PYTEST",
    "SENTIENTOS_ALLOW_NO_TESTS",
)
ALLOW_NONEXECUTION_ENV = "SENTIENTOS_ALLOW_NONEXECUTION_TEST_RUN"
SELECTION_FLAGS_WITH_VALUE = {
    "-k",
    "-m",
    "--deselect",
}
SELECTION_FLAGS_NO_VALUE = {
    "--lf",
    "--last-failed",
    "--ff",
    "--failed-first",
    "--sw",
    "--stepwise",
    "--sw-skip",
    "--stepwise-skip",
}
NON_SELECTION_FLAGS_WITH_VALUE = {
    "-c",
    "-o",
    "--maxfail",
    "--tb",
    "--durations",
    "--color",
    "--capture",
    "--rootdir",
    "--confcutdir",
    "--basetemp",
    "--log-level",
    "--log-format",
    "--log-date-format",
    "--junitxml",
    "--cov",
    "--cov-report",
    "--cov-config",
    "--cov-fail-under",
}
NON_SELECTION_FLAGS_NO_VALUE = {
    "-q",
    "-qq",
    "-v",
    "-vv",
    "-vvv",
    "-s",
    "-x",
    "-l",
    "-ra",
    "-rf",
    "-rA",
    "--disable-warnings",
    "--strict-markers",
    "--strict-config",
    "--showlocals",
    "--setup-show",
    "--setup-only",
    "--setup-plan",
}
NON_EXECUTION_COLLECT_FLAGS = {
    "--collect-only",
    "--co",
}
NON_EXECUTION_SETUP_FLAGS = {
    "--setup-only",
    "--setup-plan",
}
NON_EXECUTION_INFO_FLAGS = {
    "--fixtures",
    "--fixtures-per-test",
}


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


def _active_bypass_envs(env: dict[str, str]) -> list[str]:
    return [name for name in BYPASS_ENV_VARS if env.get(name) == "1"]


def _selection_flags(pytest_args: list[str]) -> list[str]:
    flags: list[str] = []
    idx = 0
    while idx < len(pytest_args):
        arg = pytest_args[idx]
        if arg == "--":
            flags.extend(pytest_args[idx + 1:])
            break
        if arg.startswith("-"):
            base = arg.split("=", 1)[0]
            if base in SELECTION_FLAGS_WITH_VALUE:
                flags.append(base)
                if base == arg:
                    idx += 1
            elif base in SELECTION_FLAGS_NO_VALUE:
                flags.append(base)
            elif base in NON_SELECTION_FLAGS_WITH_VALUE:
                if base == arg:
                    idx += 1
            elif base in NON_SELECTION_FLAGS_NO_VALUE:
                pass
            elif arg.startswith("-k") and arg != "-k":
                flags.append("-k")
            elif arg.startswith("-m") and arg != "-m":
                flags.append("-m")
            else:
                flags.append(base)
        else:
            flags.append(arg)
        idx += 1
    return flags


def _execution_mode(pytest_args: list[str]) -> tuple[str, list[str]]:
    seen_flags: list[str] = []
    seen_set: set[str] = set()
    idx = 0
    all_nonexecution = NON_EXECUTION_COLLECT_FLAGS | NON_EXECUTION_SETUP_FLAGS | NON_EXECUTION_INFO_FLAGS
    while idx < len(pytest_args):
        arg = pytest_args[idx]
        if arg == "--":
            break
        if arg.startswith("-"):
            base = arg.split("=", 1)[0]
            if base in all_nonexecution and base not in seen_set:
                seen_flags.append(base)
                seen_set.add(base)
        idx += 1
    if any(flag in NON_EXECUTION_COLLECT_FLAGS for flag in seen_flags):
        return "collect-only", seen_flags
    if any(flag in NON_EXECUTION_SETUP_FLAGS for flag in seen_flags):
        return "setup-only", seen_flags
    if any(flag in NON_EXECUTION_INFO_FLAGS for flag in seen_flags):
        return "info-only", seen_flags
    return "execute", seen_flags


def _run_intent(
    *,
    pytest_args: list[str],
    bypass_envs: list[str],
) -> tuple[str, list[str]]:
    selection = _selection_flags(pytest_args)
    if bypass_envs:
        return "exceptional", selection
    if selection:
        return "targeted", selection
    return "default", selection


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
    allow_nonexecution: bool,
    run_intent: str,
    selection_flags: list[str],
    allow_no_tests: bool,
    execution_mode: str,
    non_execution_flags: list[str],
    pytest_exit_code: int | None,
    tests_collected: int | None,
    tests_selected: int | None,
    tests_executed: int | None,
    exit_reason: str | None,
) -> None:
    run_dir = repo_root / "glow" / "test_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    reason = editable_status.reason
    if bypass_env:
        reason = f"{reason}+bypass-env"
    if allow_nonexecution:
        reason = f"{reason}+allow-nonexecution"
    payload: dict[str, object] = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.executable,
        "repo_root": str(repo_root),
        "git_sha": _git_sha(repo_root),
        "editable_ok": editable_status.ok,
        "editable_reason": reason,
        "bypass_env": bypass_env,
        "allow_nonexecution": allow_nonexecution,
        "install_performed": install_performed,
        "pytest_args": list(pytest_args),
        "run_intent": run_intent,
        "selection_flags": list(selection_flags),
        "allow_no_tests": allow_no_tests,
        "execution_mode": execution_mode,
        "non_execution_flags": list(non_execution_flags),
    }
    if pytest_exit_code is not None:
        payload["pytest_exit_code"] = pytest_exit_code
    if tests_collected is not None:
        payload["tests_collected"] = tests_collected
    if tests_selected is not None:
        payload["tests_selected"] = tests_selected
    if tests_executed is not None:
        payload["tests_executed"] = tests_executed
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

    env = os.environ.copy()
    bypass_envs = _active_bypass_envs(env)
    bypass_env = bool(bypass_envs)
    allow_nonexecution = env.get(ALLOW_NONEXECUTION_ENV) == "1"
    allow_no_tests = env.get("SENTIENTOS_ALLOW_NO_TESTS") == "1"
    run_intent, selection_flags = _run_intent(
        pytest_args=args.pytest_args,
        bypass_envs=bypass_envs,
    )
    execution_mode, non_execution_flags = _execution_mode(args.pytest_args)
    if allow_nonexecution:
        run_intent = "exceptional"
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
                allow_nonexecution=allow_nonexecution,
                run_intent=run_intent,
                selection_flags=selection_flags,
                allow_no_tests=allow_no_tests,
                execution_mode=execution_mode,
                non_execution_flags=non_execution_flags,
                pytest_exit_code=None,
                tests_collected=None,
                tests_selected=None,
                tests_executed=0,
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
            allow_nonexecution=allow_nonexecution,
            run_intent=run_intent,
            selection_flags=selection_flags,
            allow_no_tests=allow_no_tests,
            execution_mode=execution_mode,
            non_execution_flags=non_execution_flags,
            pytest_exit_code=None,
            tests_collected=None,
            tests_selected=None,
            tests_executed=0,
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

    _emit_run_context(
        install_performed,
        args.pytest_args,
        editable_ok=editable_status.ok,
        repo_root=REPO_ROOT,
        bypass_env="1" if bypass_env else None,
    )
    if allow_nonexecution:
        print(
            "WARNING: SENTIENTOS_ALLOW_NONEXECUTION_TEST_RUN=1 is set; "
            "CI proof guards for execution are disabled."
        )
    if env.get("SENTIENTOS_CI_REQUIRE_DEFAULT_INTENT") == "1" and run_intent != "default" and not allow_nonexecution:
        _write_provenance(
            repo_root=REPO_ROOT,
            install_performed=install_performed,
            pytest_args=args.pytest_args,
            editable_status=editable_status,
            bypass_env=bypass_env,
            allow_nonexecution=allow_nonexecution,
            run_intent=run_intent,
            selection_flags=selection_flags,
            allow_no_tests=allow_no_tests,
            execution_mode=execution_mode,
            non_execution_flags=non_execution_flags,
            pytest_exit_code=None,
            tests_collected=None,
            tests_selected=None,
            tests_executed=0,
            exit_reason="ci-default-required",
        )
        print("CI proof requires executed tests. Collection/info modes are not admissible.")
        return 1
    run_dir = REPO_ROOT / "glow" / "test_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / f"pytest_report_{uuid4().hex}.json"
    env["SENTIENTOS_PYTEST_REPORT_PATH"] = str(report_path)
    cmd = [sys.executable, "-m", "pytest"]
    cmd.extend(["-p", "scripts.pytest_collection_reporter"])
    if args.pytest_args:
        cmd.extend(args.pytest_args)
    pytest_exit_code = subprocess.run(cmd, cwd=REPO_ROOT, env=env).returncode
    tests_collected = None
    tests_selected = None
    tests_executed = None
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
        tests_collected = report.get("tests_collected")
        tests_selected = report.get("tests_selected")
        tests_executed = report.get("tests_executed")
    exit_reason = None
    if pytest_exit_code == 5:
        exit_reason = "no-tests-collected"
    elif pytest_exit_code != 0:
        exit_reason = "pytest-failed"
    if tests_executed is None:
        tests_executed = 0
    _write_provenance(
        repo_root=REPO_ROOT,
        install_performed=install_performed,
        pytest_args=args.pytest_args,
        editable_status=editable_status,
        bypass_env=bypass_env,
        allow_nonexecution=allow_nonexecution,
        run_intent=run_intent,
        selection_flags=selection_flags,
        allow_no_tests=allow_no_tests,
        execution_mode=execution_mode,
        non_execution_flags=non_execution_flags,
        pytest_exit_code=pytest_exit_code,
        tests_collected=tests_collected,
        tests_selected=tests_selected,
        tests_executed=tests_executed,
        exit_reason=exit_reason,
    )
    if (
        env.get("SENTIENTOS_CI_REQUIRE_DEFAULT_INTENT") == "1"
        and not allow_nonexecution
        and (
            run_intent != "default"
            or execution_mode != "execute"
            or tests_executed <= 0
        )
    ):
        print("CI proof requires executed tests. Collection/info modes are not admissible.")
        return 1
    if pytest_exit_code == 5 and allow_no_tests:
        print("WARNING: pytest collected 0 tests, but SENTIENTOS_ALLOW_NO_TESTS=1 overrides failure.")
        return 0
    return pytest_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
