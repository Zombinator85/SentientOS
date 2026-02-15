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
from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash

REPO_ROOT = Path(__file__).resolve().parents[1]
PRECHECK_MESSAGE = (
    "Not running against a test-capable editable install of this repo. "
    "Run pip install -e .[dev,test] or python -m scripts.run_tests."
)

TEST_INFRA_IMPORTS = (
    ("fastapi", None),
    ("starlette.testclient", "TestClient"),
    ("httpx", None),
    ("sentientos", None),
)
INSTALL_EXTRAS = "[dev,test]"
BYPASS_ENV_VARS = (
    "SENTIENTOS_ALLOW_NAKED_PYTEST",
    "SENTIENTOS_ALLOW_NO_TESTS",
)
ALLOW_NONEXECUTION_ENV = "SENTIENTOS_ALLOW_NONEXECUTION_TEST_RUN"
ALLOW_BUDGET_VIOLATION_ENV = "SENTIENTOS_ALLOW_BUDGET_VIOLATION"
MAX_SKIP_RATE_ENV = "SENTIENTOS_CI_MAX_SKIP_RATE"
MAX_XFAIL_RATE_ENV = "SENTIENTOS_CI_MAX_XFAIL_RATE"
MIN_PASSED_ENV = "SENTIENTOS_CI_MIN_PASSED"
PROVENANCE_RETENTION_LIMIT_ENV = "SENTIENTOS_PROVENANCE_RETENTION_LIMIT"
DEFAULT_MAX_SKIP_RATE = 0.20
DEFAULT_MAX_XFAIL_RATE = 0.10
DEFAULT_MIN_PASSED = 1
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


def _imports_ok() -> tuple[bool, str | None]:
    for module_name, symbol in TEST_INFRA_IMPORTS:
        if symbol:
            snippet = f"from {module_name} import {symbol}"
            label = f"{module_name}.{symbol}"
        else:
            snippet = f"import {module_name}"
            label = module_name
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            details = (proc.stderr or proc.stdout or "unknown import failure").strip()
            return False, f"{label} import failed: {details}"
    return True, None


def _install_deps() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", f".{INSTALL_EXTRAS}"],
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


def _float_env(env: dict[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"WARNING: {key}={raw!r} is not a valid float; using {default}.")
        return default


def _int_env(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"WARNING: {key}={raw!r} is not a valid integer; using {default}.")
        return default


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


def _atomic_write_json(target: Path, payload: dict[str, object]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=target.parent, encoding="utf-8") as temp_file:
        json.dump(payload, temp_file, indent=2, sort_keys=True)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.replace(target)


def _sanitize_git_sha(git_sha: str) -> str:
    compact = "".join(ch for ch in git_sha if ch.isalnum())
    return compact[:12] if compact else "unknown"


def _snapshot_file_name(*, timestamp: datetime, git_sha: str) -> str:
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{_sanitize_git_sha(git_sha)}_{uuid4().hex}.json"


def _apply_snapshot_retention(provenance_dir: Path, env: dict[str, str]) -> None:
    raw_limit = env.get(PROVENANCE_RETENTION_LIMIT_ENV)
    if raw_limit in {None, ""}:
        return
    if not isinstance(raw_limit, str):
        return
    try:
        limit = int(raw_limit)
    except ValueError:
        print(
            f"WARNING: {PROVENANCE_RETENTION_LIMIT_ENV}={raw_limit!r} is not a valid integer; retention disabled."
        )
        return
    if limit <= 0:
        print(f"WARNING: {PROVENANCE_RETENTION_LIMIT_ENV}={raw_limit!r} must be > 0; retention disabled.")
        return

    snapshots = sorted(path for path in provenance_dir.glob("*.json") if path.is_file())
    overflow = len(snapshots) - limit
    if overflow <= 0:
        return
    for stale_path in snapshots[:overflow]:
        try:
            stale_path.unlink()
        except OSError as exc:
            print(f"WARNING: failed to remove stale provenance snapshot {stale_path}: {exc}")


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
    tests_passed: int | None,
    tests_failed: int | None,
    tests_skipped: int | None,
    tests_xfailed: int | None,
    tests_xpassed: int | None,
    skip_rate: float | None,
    xfail_rate: float | None,
    budget_allow_violation: bool | None,
    budget_thresholds: dict[str, float | int] | None,
    budget_violations: list[dict[str, object]] | None,
    exit_reason: str | None,
    env: dict[str, str],
) -> None:
    run_dir = repo_root / "glow" / "test_runs"
    provenance_dir = run_dir / "provenance"
    run_dir.mkdir(parents=True, exist_ok=True)
    provenance_dir.mkdir(parents=True, exist_ok=True)
    reason = editable_status.reason
    if bypass_env:
        reason = f"{reason}+bypass-env"
    if allow_nonexecution:
        reason = f"{reason}+allow-nonexecution"
    timestamp = datetime.now(timezone.utc)
    git_sha = _git_sha(repo_root)
    payload: dict[str, object] = {
        "schema_version": 1,
        "timestamp": timestamp.isoformat(),
        "python": sys.executable,
        "repo_root": str(repo_root),
        "git_sha": git_sha,
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
    if tests_passed is not None:
        payload["tests_passed"] = tests_passed
    if tests_failed is not None:
        payload["tests_failed"] = tests_failed
    if tests_skipped is not None:
        payload["tests_skipped"] = tests_skipped
    if tests_xfailed is not None:
        payload["tests_xfailed"] = tests_xfailed
    if tests_xpassed is not None:
        payload["tests_xpassed"] = tests_xpassed
    if skip_rate is not None:
        payload["skip_rate"] = skip_rate
    if xfail_rate is not None:
        payload["xfail_rate"] = xfail_rate
    if budget_allow_violation is not None:
        payload["budget_allow_violation"] = budget_allow_violation
    if budget_thresholds is not None:
        payload["budget_thresholds"] = budget_thresholds
    if budget_violations is not None:
        payload["budget_violations"] = budget_violations
    if exit_reason:
        payload["exit_reason"] = exit_reason

    prev_provenance_hash: str | None = None
    chain_status: str | None = None
    snapshots = sorted(path for path in provenance_dir.glob("*.json") if path.is_file())
    if snapshots:
        previous_path = snapshots[-1]
        try:
            previous_payload = json.loads(previous_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            chain_status = f"previous snapshot unreadable: {previous_path.name}"
        else:
            previous_hash = previous_payload.get("provenance_hash")
            if isinstance(previous_hash, str) and len(previous_hash) == 64:
                prev_provenance_hash = previous_hash
            else:
                chain_status = f"previous snapshot missing/invalid provenance_hash: {previous_path.name}"

    payload["hash_algo"] = HASH_ALGO
    payload["prev_provenance_hash"] = prev_provenance_hash
    payload["provenance_hash"] = compute_provenance_hash(payload, prev_provenance_hash)
    if chain_status:
        payload["chain_status"] = chain_status

    latest_target = run_dir / "test_run_provenance.json"
    snapshot_target = provenance_dir / _snapshot_file_name(timestamp=timestamp, git_sha=git_sha)

    _atomic_write_json(latest_target, payload)
    _atomic_write_json(snapshot_target, payload)
    _apply_snapshot_retention(provenance_dir, env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install SentientOS dev/test deps (if needed) and run pytest.",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Arguments forwarded to pytest.",
    )
    args, passthrough_pytest_args = parser.parse_known_args(argv)

    pytest_args = list(args.pytest_args) + list(passthrough_pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    env = os.environ.copy()
    bypass_envs = _active_bypass_envs(env)
    bypass_env = bool(bypass_envs)
    allow_nonexecution = env.get(ALLOW_NONEXECUTION_ENV) == "1"
    allow_no_tests = env.get("SENTIENTOS_ALLOW_NO_TESTS") == "1"
    run_intent, selection_flags = _run_intent(
        pytest_args=pytest_args,
        bypass_envs=bypass_envs,
    )
    execution_mode, non_execution_flags = _execution_mode(pytest_args)
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
                pytest_args=pytest_args,
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
                tests_passed=0,
                tests_failed=0,
                tests_skipped=0,
                tests_xfailed=0,
                tests_xpassed=0,
                skip_rate=0.0,
                xfail_rate=0.0,
                budget_allow_violation=None,
                budget_thresholds=None,
                budget_violations=None,
                exit_reason="install-failed",
                env=env,
            )
            _emit_run_context(
                install_performed,
                pytest_args,
                editable_ok=editable_status.ok,
                repo_root=REPO_ROOT,
                bypass_env="1" if bypass_env else None,
            )
            print(PRECHECK_MESSAGE)
            return 1

    editable_status = get_editable_install_status(REPO_ROOT)
    imports_ok, import_error = _imports_ok()
    if not editable_status.ok or not imports_ok:
        _write_provenance(
            repo_root=REPO_ROOT,
            install_performed=install_performed,
            pytest_args=pytest_args,
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
            tests_passed=0,
            tests_failed=0,
            tests_skipped=0,
            tests_xfailed=0,
            tests_xpassed=0,
            skip_rate=0.0,
            xfail_rate=0.0,
            budget_allow_violation=None,
            budget_thresholds=None,
            budget_violations=None,
            exit_reason="airlock-failed",
            env=env,
        )
        _emit_run_context(
            install_performed,
            pytest_args,
            editable_ok=editable_status.ok,
            repo_root=REPO_ROOT,
            bypass_env="1" if bypass_env else None,
        )
        if import_error:
            print(f"run_tests import airlock failed: {import_error}")
        print(PRECHECK_MESSAGE)
        return 1

    _emit_run_context(
        install_performed,
        pytest_args,
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
            pytest_args=pytest_args,
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
            tests_passed=0,
            tests_failed=0,
            tests_skipped=0,
            tests_xfailed=0,
            tests_xpassed=0,
            skip_rate=0.0,
            xfail_rate=0.0,
            budget_allow_violation=None,
            budget_thresholds=None,
            budget_violations=None,
            exit_reason="ci-default-required",
            env=env,
        )
        print("CI proof requires executed tests. Collection/info modes are not admissible.")
        return 1
    run_dir = REPO_ROOT / "glow" / "test_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / f"pytest_report_{uuid4().hex}.json"
    env["SENTIENTOS_PYTEST_REPORT_PATH"] = str(report_path)
    cmd = [sys.executable, "-m", "pytest"]
    cmd.extend(["-p", "scripts.pytest_collection_reporter"])
    if pytest_args:
        cmd.extend(pytest_args)
    pytest_exit_code = subprocess.run(cmd, cwd=REPO_ROOT, env=env).returncode
    tests_collected = None
    tests_selected = None
    tests_executed = None
    tests_passed = None
    tests_failed = None
    tests_skipped = None
    tests_xfailed = None
    tests_xpassed = None
    skip_rate = None
    xfail_rate = None
    budget_thresholds = None
    budget_violations: list[dict[str, object]] | None = None
    budget_allow_violation = env.get(ALLOW_BUDGET_VIOLATION_ENV) == "1"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
        tests_collected = report.get("tests_collected")
        tests_selected = report.get("tests_selected")
        tests_executed = report.get("tests_executed")
        tests_passed = report.get("tests_passed")
        tests_failed = report.get("tests_failed")
        tests_skipped = report.get("tests_skipped")
        tests_xfailed = report.get("tests_xfailed")
        tests_xpassed = report.get("tests_xpassed")
    if tests_executed is None:
        tests_executed = 0
    if tests_passed is None:
        tests_passed = 0
    if tests_failed is None:
        tests_failed = 0
    if tests_skipped is None:
        tests_skipped = 0
    if tests_xfailed is None:
        tests_xfailed = 0
    if tests_xpassed is None:
        tests_xpassed = 0
    total_outcomes = tests_passed + tests_failed + tests_skipped + tests_xfailed + tests_xpassed
    if total_outcomes > 0:
        skip_rate = tests_skipped / total_outcomes
        xfail_rate = tests_xfailed / total_outcomes
    else:
        skip_rate = 0.0
        xfail_rate = 0.0
    budget_thresholds = {
        "min_passed": _int_env(env, MIN_PASSED_ENV, DEFAULT_MIN_PASSED),
        "max_skip_rate": _float_env(env, MAX_SKIP_RATE_ENV, DEFAULT_MAX_SKIP_RATE),
        "max_xfail_rate": _float_env(env, MAX_XFAIL_RATE_ENV, DEFAULT_MAX_XFAIL_RATE),
    }
    budget_violations = []
    if tests_failed != 0:
        budget_violations.append(
            {
                "metric": "tests_failed",
                "value": tests_failed,
                "threshold": 0,
                "rule": "== 0",
            }
        )
    if tests_xpassed != 0:
        budget_violations.append(
            {
                "metric": "tests_xpassed",
                "value": tests_xpassed,
                "threshold": 0,
                "rule": "== 0",
            }
        )
    if tests_passed < budget_thresholds["min_passed"]:
        budget_violations.append(
            {
                "metric": "tests_passed",
                "value": tests_passed,
                "threshold": budget_thresholds["min_passed"],
                "rule": f">= {budget_thresholds['min_passed']}",
            }
        )
    if skip_rate > budget_thresholds["max_skip_rate"]:
        budget_violations.append(
            {
                "metric": "skip_rate",
                "value": skip_rate,
                "threshold": budget_thresholds["max_skip_rate"],
                "rule": f"<= {budget_thresholds['max_skip_rate']}",
            }
        )
    if xfail_rate > budget_thresholds["max_xfail_rate"]:
        budget_violations.append(
            {
                "metric": "xfail_rate",
                "value": xfail_rate,
                "threshold": budget_thresholds["max_xfail_rate"],
                "rule": f"<= {budget_thresholds['max_xfail_rate']}",
            }
        )
    exit_reason = None
    if pytest_exit_code == 5:
        exit_reason = "no-tests-collected"
    elif pytest_exit_code != 0:
        exit_reason = "pytest-failed"
    if budget_allow_violation:
        run_intent = "exceptional"
        print(
            "WARNING: SENTIENTOS_ALLOW_BUDGET_VIOLATION=1 is set; "
            "budget enforcement is overridden and this run is marked exceptional."
        )
    _write_provenance(
        repo_root=REPO_ROOT,
        install_performed=install_performed,
        pytest_args=pytest_args,
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
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        tests_skipped=tests_skipped,
        tests_xfailed=tests_xfailed,
        tests_xpassed=tests_xpassed,
        skip_rate=skip_rate,
        xfail_rate=xfail_rate,
        budget_allow_violation=budget_allow_violation,
        budget_thresholds=budget_thresholds,
        budget_violations=budget_violations,
        exit_reason=exit_reason,
        env=env,
    )
    proof_mode = env.get("SENTIENTOS_CI_REQUIRE_DEFAULT_INTENT") == "1"
    if proof_mode and budget_allow_violation:
        print(
            "ERROR: SENTIENTOS_ALLOW_BUDGET_VIOLATION=1 is not admissible in CI proof mode."
        )
        return 1
    if (
        proof_mode
        and not allow_nonexecution
        and (
            run_intent != "default"
            or execution_mode != "execute"
            or tests_executed <= 0
        )
    ):
        print("CI proof requires executed tests. Collection/info modes are not admissible.")
        return 1
    if proof_mode and not allow_nonexecution and budget_violations:
        print("CI proof budget requirements were not met:")
        for violation in budget_violations:
            metric = violation.get("metric")
            value = violation.get("value")
            rule = violation.get("rule")
            threshold = violation.get("threshold")
            print(f"  - {metric}={value} violates {rule} (threshold={threshold})")
        return 1
    if pytest_exit_code == 5 and allow_no_tests:
        print("WARNING: pytest collected 0 tests, but SENTIENTOS_ALLOW_NO_TESTS=1 overrides failure.")
        return 0
    return pytest_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
