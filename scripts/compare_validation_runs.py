from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from typing import Any

from scripts.analyze_test_failures import _extract_failures
from sentientos.forge_failures import semantic_failure_signature
from sentientos.validation_causality import (
    SCHEMA,
    command_contract_digest,
    compare_runs,
    digest_json,
    environment_digest,
)

_GENERATED_PREFIXES = ("glow/", "pulse/", "sentientos_data/runtime/", "sentientos_data/vow/")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"git_{args[0]}_failed:{result.stderr.decode('utf-8', 'replace')[-500:]}")
    return result.stdout.decode("utf-8", "replace").strip()


def workspace_identity(repo: Path, *, head_sha: str) -> str:
    """Hash tracked edits and intended untracked source files, excluding runtime output."""
    diff = subprocess.run(
        ["git", "diff", "--binary", head_sha, "--", ".", ":(exclude)glow/**", ":(exclude)pulse/**", ":(exclude)sentientos_data/**"],
        cwd=repo, capture_output=True, check=False,
    )
    if diff.returncode:
        raise ValueError("git_diff_failed")
    chunks = [b"tracked-diff\0", diff.stdout]
    paths = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=repo, capture_output=True, check=False)
    if paths.returncode:
        raise ValueError("git_untracked_list_failed")
    for raw in sorted(path for path in paths.stdout.split(b"\0") if path):
        name = raw.decode("utf-8", "surrogateescape")
        if name.startswith(_GENERATED_PREFIXES):
            continue
        path = repo / name
        if path.is_symlink():
            target = os.readlink(path).encode("utf-8", "surrogateescape")
            chunks.extend((b"untracked-symlink\0", raw, b"\0", target))
        elif path.is_file():
            mode = stat.S_IMODE(path.stat().st_mode)
            chunks.extend((b"untracked-file\0", raw, b"\0", oct(mode).encode("ascii"), b"\0", hashlib.sha256(path.read_bytes()).digest()))
    return _sha256(b"".join(chunks))


def _environment(root: Path) -> dict[str, Any]:
    packages = []
    for dist in importlib.metadata.distributions():
        names = dist.metadata.get_all("Name")
        name = names[0] if names else None
        version = dist.version
        if isinstance(name, str):
            packages.append([name.lower().replace("_", "-"), version])
    packages.sort()
    lock = root / "requirements.lock"
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "packages": packages,
        "requirements_lock_sha256": _sha256(lock.read_bytes()) if lock.is_file() else None,
    }


def _safe_extract_archive(repo: Path, sha: str, target: Path) -> str:
    tree_sha = _git(repo, "rev-parse", "--verify", f"{sha}^{{tree}}")
    archive = subprocess.run(["git", "archive", "--format=tar", sha], cwd=repo, capture_output=True, check=False)
    if archive.returncode:
        raise ValueError("git_archive_failed")
    with tarfile.open(fileobj=__import__("io").BytesIO(archive.stdout), mode="r:") as tar:
        root = target.resolve()
        for member in tar.getmembers():
            destination = (target / member.name).resolve()
            if destination != root and root not in destination.parents:
                raise ValueError("unsafe_archive_member")
        tar.extractall(target, filter="data")
    return tree_sha


def _environment_for_root(base: dict[str, Any], root: Path) -> dict[str, Any]:
    current = dict(base)
    lock = root / "requirements.lock"
    current["requirements_lock_sha256"] = _sha256(lock.read_bytes()) if lock.is_file() else None
    return current


def _run_one(
    *, root: Path, repository_sha: str, source_identity: str,
    nodes: list[str], contract: list[str], env_identity: dict[str, Any],
    label: str, output_root: Path, timeout_seconds: int,
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    argv = [sys.executable, "-m", "scripts.run_tests", "-q", *nodes]
    env = os.environ.copy()
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.Popen(
        argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    timeout_error: subprocess.TimeoutExpired | None = None
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        timeout_error = exc
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
    finished = datetime.now(timezone.utc).isoformat()
    if timeout_error is not None:
        def _tail(value: str | bytes | None) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", "replace")[-8000:]
            return value[-8000:] if isinstance(value, str) else ""

        raw_contract = [sys.executable, "-m", "scripts.run_tests", "-q", *nodes]
        return {
            "repository_sha": repository_sha,
            "workspace_identity": source_identity,
            "command_contract_digest": command_contract_digest(raw_contract),
            "command_contract": {"runner": "scripts.run_tests", "argv": raw_contract},
            "environment_digest": environment_digest(env_identity),
            "environment_identity": env_identity,
            "run_id": run_id,
            "started_at": started,
            "finished_at": finished,
            "exit_code": 124,
            "complete": False,
            "tests_collected": 0,
            "tests_executed": 0,
            "tests_failed": 0,
            "reporter_ok": False,
            "metrics_status": "timed_out",
            "junit_sha256": _sha256(b""),
            "run_tests_provenance_sha256": "",
            "run_tests_timeout_seconds": timeout_seconds,
            "normalized_failure_multiset": [],
            "raw_stdout_tail": _tail(stdout or timeout_error.stdout),
            "raw_stderr_tail": _tail(stderr or timeout_error.stderr),
        }
    return_code = proc.returncode
    provenance_path = root / "glow" / "test_runs" / "test_run_provenance.json"
    if not provenance_path.is_file():
        detail = (stdout + "\n" + stderr)[-1200:]
        raise ValueError(f"{label}_provenance_missing:exit={return_code}:{detail}")
    raw_provenance = provenance_path.read_bytes()
    try:
        test_provenance = json.loads(raw_provenance.decode("utf-8"))
        junit = Path(str(test_provenance["junitxml_path"]))
        if not junit.is_absolute():
            junit = root / junit
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"{label}_provenance_invalid:{type(exc).__name__}") from exc
    if not junit.is_file():
        raise ValueError(f"{label}_junit_missing")
    raw_junit = junit.read_bytes()
    # Comparison identity must not depend on the three-line display excerpt used by
    # the human-facing failure digest.
    failures = _extract_failures(junit, max_message_lines=None)
    counter: Counter[str] = Counter()
    rows: dict[str, dict[str, Any]] = {}
    for failure in failures:
        message = "\n".join(failure.message_lines)
        signature = semantic_failure_signature(failure.nodeid, failure.exception_type, message)
        counter[signature] += 1
        rows[signature] = {
            "signature": signature,
            "nodeid": failure.nodeid,
            "exception_type": failure.exception_type,
            "message": message,
        }
    normalized = [dict(rows[sig], count=counter[sig]) for sig in sorted(counter)]
    suites = []
    # ElementTree is used by the shared parser above; aggregate counts from JUnit itself.
    import xml.etree.ElementTree as ET
    tree = ET.parse(junit)
    for suite in tree.findall(".//testsuite"):
        suites.append(suite)
    collected = sum(int(suite.get("tests", "0")) for suite in suites)
    tests_executed = sum(1 for case in tree.findall(".//testcase") if not case.findall("skipped"))
    if not collected or return_code not in (0, 1) or ((return_code == 0) != (len(failures) == 0)):
        complete = False
    else:
        complete = True
    raw_contract = [sys.executable, "-m", "scripts.run_tests", "-q", *nodes]
    actual_failed = test_provenance.get("tests_failed")
    actual_collected = test_provenance.get("tests_collected")
    actual_executed = test_provenance.get("tests_executed")
    reporter_ok = test_provenance.get("reporter_ok") is True and test_provenance.get("metrics_status") == "ok"
    complete = (
        complete and reporter_ok and actual_failed == len(failures)
        and actual_collected == collected and isinstance(actual_executed, int)
        and actual_executed > 0
    )
    run: dict[str, Any] = {
        "repository_sha": repository_sha,
        "workspace_identity": source_identity,
        "command_contract_digest": command_contract_digest(raw_contract),
        "command_contract": {"runner": "scripts.run_tests", "argv": raw_contract},
        "environment_digest": environment_digest(env_identity),
        "environment_identity": env_identity,
        "run_id": test_provenance.get("run_id", run_id),
        "started_at": started,
        "finished_at": finished,
        "exit_code": return_code,
        "complete": complete,
        "tests_collected": actual_collected if isinstance(actual_collected, int) else collected,
        "tests_executed": actual_executed if isinstance(actual_executed, int) else tests_executed,
        "tests_failed": actual_failed if isinstance(actual_failed, int) else len(failures),
        "reporter_ok": reporter_ok,
        "metrics_status": str(test_provenance.get("metrics_status", "unavailable")),
        "junit_sha256": _sha256(raw_junit),
        "run_tests_provenance_sha256": _sha256(raw_provenance),
        "runner_reported_repository_sha": test_provenance.get("git_sha"),
        "normalized_failure_multiset": normalized,
        "raw_stdout_tail": stdout[-8000:],
        "raw_stderr_tail": stderr[-8000:],
    }
    return run


def compare_repository_runs(
    *, repository_root: Path, base_sha: str, candidate_sha: str,
    candidate_root: Path, nodes: list[str], output_path: Path,
    timeout_seconds: int = 1200,
) -> dict[str, Any]:
    if _git(repository_root, "rev-parse", "HEAD") != candidate_sha:
        raise ValueError("candidate_sha_is_not_checkout_head")
    if _git(repository_root, "rev-parse", base_sha) != base_sha:
        raise ValueError("immutable_base_sha_not_found")
    candidate_identity = workspace_identity(candidate_root, head_sha=candidate_sha)
    contract = ["scripts.run_tests", "-q", *nodes]
    env_candidate = _environment(candidate_root)
    base_environment: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="sentientos-causal-base-") as base_tmp, tempfile.TemporaryDirectory(prefix="sentientos-causal-output-") as outputs:
        base_root = Path(base_tmp) / "source"
        base_root.mkdir()
        base_tree = _safe_extract_archive(repository_root, base_sha, base_root)
        env_base = _environment_for_root(env_candidate, base_root)
        base_identity = digest_json({"git_tree_sha": base_tree})
        install_cmd = [sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e"]
        try:
            base_install = subprocess.run([*install_cmd, str(base_root)], cwd=repository_root, capture_output=True, text=True, check=False)
            if base_install.returncode:
                raise ValueError(f"base_editable_install_failed:{base_install.stderr[-1000:]}")
            base_run = _run_one(root=base_root, repository_sha=base_sha, source_identity=base_identity, nodes=nodes, contract=contract, env_identity=env_base, label="base", output_root=Path(outputs), timeout_seconds=timeout_seconds)
        finally:
            candidate_install = subprocess.run([*install_cmd, str(candidate_root)], cwd=repository_root, capture_output=True, text=True, check=False)
            if candidate_install.returncode:
                raise ValueError(f"candidate_editable_restore_failed:{candidate_install.stderr[-1000:]}")
        candidate_run = _run_one(root=candidate_root, repository_sha=candidate_sha, source_identity=candidate_identity, nodes=nodes, contract=contract, env_identity=env_candidate, label="candidate", output_root=Path(outputs), timeout_seconds=timeout_seconds)
        base_environment = env_base
    evidence = compare_runs(
        immutable_base_sha=base_sha,
        candidate_sha=candidate_sha,
        candidate_workspace_identity=candidate_identity,
        base_run=base_run,
        candidate_run=candidate_run,
    )
    evidence["base_source_tree_sha"] = base_tree
    evidence["base_environment_identity"] = base_environment
    evidence["candidate_environment_identity"] = env_candidate
    evidence.pop("comparison_digest", None)
    evidence["comparison_digest"] = digest_json(evidence)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an immutable-base versus candidate pytest comparison.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate-root", type=Path, default=Path.cwd())
    parser.add_argument("--base-sha", required=True, help="Immutable reviewed base SHA; never refreshed from candidate output.")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--node", action="append", default=[], dest="nodes", help="Optional pytest node/path selection; omit to compare the full default scripts.run_tests -q suite.")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_repository_runs(
            repository_root=args.repository_root.resolve(), base_sha=args.base_sha,
            candidate_sha=args.candidate_sha, candidate_root=args.candidate_root.resolve(),
            nodes=args.nodes, output_path=args.output, timeout_seconds=args.timeout_seconds,
        )
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        failed: dict[str, Any] = {
            "schema_version": SCHEMA,
            "immutable_base_sha": args.base_sha,
            "candidate_sha": args.candidate_sha,
            "status": "comparison_incomplete",
            "reasons": [f"comparison_execution_failed:{type(exc).__name__}:{exc}"],
        }
        failed["comparison_digest"] = digest_json(failed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(failed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"schema_version": SCHEMA, "status": "comparison_incomplete", "reasons": failed["reasons"]}, sort_keys=True))
        return 2
    print(json.dumps({"status": result["status"], "comparison_digest": result["comparison_digest"], "matched": result["matched_preexisting_failures"], "new": result["new_candidate_failures"], "retired": result["retired_or_improved_failures"]}, sort_keys=True))
    return 1 if result["status"] not in {"no_regression", "improved"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
