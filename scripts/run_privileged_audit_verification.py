from __future__ import annotations

"""Run required audit checks as root and bind results to the exact Git source."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


SOURCE_FILES = (
    "scripts/run_privileged_audit_verification.py",
    "verify_audits.py",
    "scripts/verify_audits.py",
    "scripts/audit_immutability_verifier.py",
    "sentientos/admin_utils.py",
    "sentientos/privilege/__init__.py",
    "vow/immutable_manifest.json",
)
RESULT_FILES = (
    "glow/audits/verify_audits_result.json",
    "glow/audits/audit_immutability_result.json",
    "glow/contracts/final_strict_audit_digest.json",
    "glow/contracts/strict_audit_status.json",
    "glow/contracts/strict_audit_breakdown.json",
)


def _git(root: Path, *args: str) -> str:
    environment = os.environ.copy()
    environment.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": str(root),
    })
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=True,
        capture_output=True, text=True, env=environment,
    )
    return result.stdout.strip()


def _source_digests(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative in SOURCE_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"verification_source_unavailable:{relative}")
        digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _result_digests(root: Path) -> dict[str, str | None]:
    results: dict[str, str | None] = {}
    for relative in RESULT_FILES:
        path = root / relative
        results[relative] = (
            hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file() and not path.is_symlink() else None
        )
    return results


def _command_record(command: list[str], root: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command, cwd=root, capture_output=True, text=True, check=False,
        env=os.environ.copy(),
    )
    stdout = completed.stdout.encode("utf-8", errors="replace")
    stderr = completed.stderr.encode("utf-8", errors="replace")
    return {
        "argv": command,
        "exit_code": completed.returncode,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
    }


def run_verification(root: Path, *, expected_sha: str, output: Path) -> dict[str, Any]:
    if os.name != "posix" or os.geteuid() != 0:
        raise PermissionError("privileged_audit_verification_requires_actual_root")
    root = root.resolve(strict=True)
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    if head != expected_sha:
        raise RuntimeError("verification_head_does_not_match_expected_sha")
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("verification_checkout_has_tracked_changes")
    source_before = _source_digests(root)

    commands = [
        [sys.executable, "verify_audits.py", "--strict"],
        [sys.executable, "scripts/audit_immutability_verifier.py"],
    ]
    command_results = [_command_record(command, root) for command in commands]
    source_after = _source_digests(root)
    final_head = _git(root, "rev-parse", "HEAD")
    final_tree = _git(root, "rev-parse", "HEAD^{tree}")
    source_unchanged = source_before == source_after
    identity_unchanged = head == final_head and tree == final_tree
    checks_passed = all(item["exit_code"] == 0 for item in command_results)
    report: dict[str, Any] = {
        "schema_version": 1,
        "tool": "privileged_audit_verification",
        "status": "passed" if checks_passed and source_unchanged and identity_unchanged else "failed",
        "administrator_verified": True,
        "effective_uid": os.geteuid(),
        "expected_sha": expected_sha,
        "source_sha": head,
        "source_tree": tree,
        "source_files_sha256": source_before,
        "source_unchanged": source_unchanged,
        "repository_identity_unchanged": identity_unchanged,
        "commands": command_results,
        "result_artifact_sha256": _result_digests(root),
    }
    output_path = output if output.is_absolute() else root / output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path,
        default=Path("glow/audits/privileged_audit_verification.json"))
    args = parser.parse_args(argv)
    try:
        report = run_verification(
            args.repo_root, expected_sha=args.expected_sha, output=args.output)
    except Exception as exc:
        print(json.dumps({
            "tool": "privileged_audit_verification",
            "status": "error",
            "reason": f"{type(exc).__name__}:{exc}"[:256],
        }, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({
        "tool": report["tool"], "status": report["status"],
        "source_sha": report["source_sha"], "source_tree": report["source_tree"],
        "effective_uid": report["effective_uid"],
    }, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
