from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.editable_install import get_editable_install_status

PROFILES = ("local-dev-relaxed", "ci-advisory", "federation-enforce")
DEFAULT_OUTPUT = Path("glow/contracts/protected_corridor_report.json")
INSTALL_EXTRAS = ".[dev,test]"

PREREQUISITE_LABELS: dict[str, str] = {
    "editable_install": "Repository is installed as editable package from this repo root.",
    "test_runtime_imports": "pytest + FastAPI/Starlette/httpx runtime imports are available.",
}

TEST_RUNTIME_IMPORTS: tuple[tuple[str, str | None], ...] = (
    ("pytest", None),
    ("fastapi", None),
    ("starlette.testclient", "TestClient"),
    ("httpx", None),
)


@dataclass(frozen=True)
class CorridorCheck:
    name: str
    command: tuple[str, ...]
    blocking: bool
    expected_relaxed: str
    notes: str
    prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: tuple[str, ...]
    returncode: int
    outcome: str
    bucket: str
    blocking: bool
    expected_in_profile: str
    note: str
    output_excerpt: str


@dataclass(frozen=True)
class PrerequisiteStatus:
    ready: bool
    checks: dict[str, list[str]]
    diagnostics: list[str]


CHECKS: tuple[CorridorCheck, ...] = (
    CorridorCheck(
        name="constitution_verify",
        command=("python", "-m", "sentientos.ops", "constitution", "verify", "--json"),
        blocking=True,
        expected_relaxed="pass",
        notes="Constitutional surface must remain green across profiles.",
    ),
    CorridorCheck(
        name="forge_status",
        command=("python", "-m", "sentientos.ops", "forge", "status", "--json"),
        blocking=True,
        expected_relaxed="warn",
        notes="Local relaxed profile may report degraded repository artifacts in clean workspaces.",
    ),
    CorridorCheck(
        name="forge_replay",
        command=("python", "-m", "sentientos.ops", "forge", "replay", "--verify", "--last-n", "20", "--emit-snapshot", "1"),
        blocking=True,
        expected_relaxed="pass",
        notes="Replay consistency required for release corridor.",
    ),
    CorridorCheck(
        name="contract_status",
        command=("python", "scripts/emit_contract_status.py"),
        blocking=True,
        expected_relaxed="pass",
        notes="Contract status artifact must emit deterministically.",
    ),
    CorridorCheck(
        name="contract_status_rollup_targeted",
        command=("python", "-m", "scripts.run_tests", "-q", "tests/test_contract_status_rollup.py"),
        blocking=True,
        expected_relaxed="pass",
        notes="Contract status rollup invariants are release-critical for operator visibility.",
        prerequisites=("editable_install", "test_runtime_imports"),
    ),
    CorridorCheck(
        name="contract_drift",
        command=("python", "scripts/contract_drift.py"),
        blocking=False,
        expected_relaxed="warn",
        notes="Current repo keeps baseline/deployment artifacts outside local corridor.",
    ),
    CorridorCheck(
        name="simulation_baseline_gate",
        command=("python", "-m", "sentientos.ops", "simulate", "federation", "--baseline", "--json"),
        blocking=True,
        expected_relaxed="pass",
        notes="Federation simulation baseline gate.",
    ),
    CorridorCheck(
        name="formal_verification",
        command=("python", "-m", "sentientos.ops", "verify", "formal", "--json"),
        blocking=True,
        expected_relaxed="pass",
        notes="Formal wing bounded model checks.",
    ),
    CorridorCheck(
        name="federation_hardening_targeted",
        command=("python", "-m", "scripts.run_tests", "-q", "tests/test_federation_guard_cathedral.py", "sentientos/tests/test_federation_integrity.py"),
        blocking=True,
        expected_relaxed="pass",
        notes="Targeted federation hardening checks.",
        prerequisites=("editable_install", "test_runtime_imports"),
    ),
    CorridorCheck(
        name="operator_cli_targeted",
        command=("python", "-m", "scripts.run_tests", "-q", "tests/test_operator_cli_hygiene.py", "sentientos/tests/test_ops_cli.py"),
        blocking=True,
        expected_relaxed="pass",
        notes="Operator/CLI visibility and hygiene checks.",
        prerequisites=("editable_install", "test_runtime_imports"),
    ),
    CorridorCheck(
        name="mypy_protected_scope",
        command=("python", "scripts/mypy_ratchet.py"),
        blocking=False,
        expected_relaxed="warn",
        notes="Typing debt outside protected scope is tracked as deferred debt.",
    ),
    CorridorCheck(
        name="audit_immutability_verifier",
        command=("python", "scripts/audit_immutability_verifier.py"),
        blocking=True,
        expected_relaxed="pass",
        notes="Immutable manifest verification.",
    ),
    CorridorCheck(
        name="verify_audits_strict",
        command=("python", "scripts/verify_audits.py", "--strict"),
        blocking=False,
        expected_relaxed="warn",
        notes="Known historical/runtime split may produce advisory audit-chain warnings.",
    ),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_command(command: Sequence[str], env: dict[str, str]) -> tuple[int, str]:
    completed = subprocess.run(command, capture_output=True, text=True, env=env)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def _import_snippet(module_name: str, symbol: str | None) -> str:
    if symbol:
        return f"from {module_name} import {symbol}"
    return f"import {module_name}"


def _test_runtime_imports_ok(repo_root: Path) -> tuple[bool, list[str]]:
    diagnostics: list[str] = []
    for module_name, symbol in TEST_RUNTIME_IMPORTS:
        proc = subprocess.run(
            [sys.executable, "-c", _import_snippet(module_name, symbol)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            label = f"{module_name}.{symbol}" if symbol else module_name
            detail = (proc.stderr or proc.stdout or "unknown import failure").strip()
            diagnostics.append(f"{label} import failed: {detail}")
    return (len(diagnostics) == 0), diagnostics


def check_prerequisites(*, checks: Sequence[CorridorCheck] = CHECKS, repo_root: Path = Path(".")) -> PrerequisiteStatus:
    missing_by_key: dict[str, str] = {}
    diagnostics: list[str] = []

    editable_status = get_editable_install_status(repo_root.resolve())
    if not editable_status.ok:
        missing_by_key["editable_install"] = f"editable install check failed ({editable_status.reason})"

    imports_ok, import_diagnostics = _test_runtime_imports_ok(repo_root)
    if not imports_ok:
        missing_by_key["test_runtime_imports"] = "required test runtime imports unavailable"
        diagnostics.extend(import_diagnostics)

    check_missing: dict[str, list[str]] = {}
    for check in checks:
        missing_for_check = [key for key in check.prerequisites if key in missing_by_key]
        if missing_for_check:
            check_missing[check.name] = missing_for_check

    for key, message in missing_by_key.items():
        diagnostics.append(f"{key}: {message}")

    return PrerequisiteStatus(
        ready=not check_missing,
        checks=check_missing,
        diagnostics=diagnostics,
    )


def bootstrap_prerequisites(*, repo_root: Path = Path(".")) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", INSTALL_EXTRAS],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


def _expected_for_profile(check: CorridorCheck, profile: str) -> str:
    if profile == "local-dev-relaxed":
        return check.expected_relaxed
    if profile == "ci-advisory" and not check.blocking:
        return "warn"
    if profile == "federation-enforce" and not check.blocking and check.name != "contract_drift":
        return "warn"
    return "pass"


def classify_result(check: CorridorCheck, *, profile: str, returncode: int, output: str) -> CheckResult:
    expected = _expected_for_profile(check, profile)
    outcome = "pass" if returncode == 0 else "warn"
    if returncode != 0 and (
        "Not running against a test-capable editable install" in output
        or "run_tests import airlock failed" in output
        or "No module named 'fastapi'" in output
        or "No module named 'starlette'" in output
        or "No module named 'httpx'" in output
    ):
        bucket = "environment_unprovisioned"
    elif returncode != 0 and (
        "CI proof requires executed tests" in output
        or "Collection/info modes are not admissible" in output
    ):
        bucket = "policy_doctrine_skipped"
    elif returncode != 0 and expected == "pass":
        bucket = "blocking_release_corridor_failure" if check.blocking else "blocking_correctness_failure"
    elif returncode != 0 and check.name == "verify_audits_strict":
        bucket = "non_blocking_optional_historical_runtime_state"
    elif returncode != 0 and check.name in {"mypy_protected_scope", "contract_drift"}:
        bucket = "legacy_deferred_debt"
    else:
        bucket = "pass"

    note = check.notes
    if check.name == "verify_audits_strict" and returncode != 0 and "audit_chain_status" in output:
        note = "Audit chain history reported broken while runtime split remains valid; kept advisory."

    excerpt = " | ".join([line.strip() for line in output.splitlines() if line.strip()][:3])

    return CheckResult(
        name=check.name,
        command=check.command,
        returncode=returncode,
        outcome=outcome,
        bucket=bucket,
        blocking=check.blocking,
        expected_in_profile=expected,
        note=note,
        output_excerpt=excerpt,
    )


def run_profile(profile: str, *, checks: Sequence[CorridorCheck] = CHECKS) -> dict[str, Any]:
    env = os.environ.copy()
    env["SENTIENTOS_ENFORCEMENT_PROFILE"] = profile
    env.setdefault("PYTHONPATH", ".")

    results: list[CheckResult] = []
    for check in checks:
        rc, output = _run_command(check.command, env)
        results.append(classify_result(check, profile=profile, returncode=rc, output=output))

    blocking_failures = [asdict(item) for item in results if item.bucket.startswith("blocking_")]
    provisioning_failures = [asdict(item) for item in results if item.bucket == "environment_unprovisioned"]
    doctrine_skips = [asdict(item) for item in results if item.bucket == "policy_doctrine_skipped"]
    non_blocking_failures = [asdict(item) for item in results if item.bucket in {"legacy_deferred_debt", "non_blocking_optional_historical_runtime_state"}]
    passed = [asdict(item) for item in results if item.bucket == "pass"]

    health = "green"
    if blocking_failures or provisioning_failures:
        health = "red"
    elif non_blocking_failures:
        health = "amber"

    return {
        "profile": profile,
        "executed_at": _iso_now(),
        "checks": [asdict(item) for item in results],
        "summary": {
            "check_count": len(results),
            "pass_count": len(passed),
            "blocking_failure_count": len(blocking_failures),
            "provisioning_failure_count": len(provisioning_failures),
            "policy_skip_count": len(doctrine_skips),
            "non_blocking_failure_count": len(non_blocking_failures),
            "repo_health": health,
        },
        "blocking_failures": blocking_failures,
        "provisioning_failures": provisioning_failures,
        "policy_skips": doctrine_skips,
        "non_blocking_failures": non_blocking_failures,
        "deferred_debt": [entry for entry in non_blocking_failures if entry["bucket"] == "legacy_deferred_debt"],
    }


def run_validation(*, profiles: Sequence[str], output_path: Path, prerequisite_status: PrerequisiteStatus | None = None) -> dict[str, Any]:
    status = prerequisite_status or check_prerequisites()
    report = {
        "schema_version": 1,
        "provisioning": {
            "ready": status.ready,
            "check_missing_prerequisites": status.checks,
            "diagnostics": status.diagnostics,
            "prerequisite_labels": PREREQUISITE_LABELS,
        },
        "protected_corridor": {
            "definition": [
                {
                    "name": check.name,
                    "command": list(check.command),
                    "blocking": check.blocking,
                    "notes": check.notes,
                    "prerequisites": list(check.prerequisites),
                }
                for check in CHECKS
            ]
        },
        "profiles": [run_profile(profile) for profile in profiles] if status.ready else [],
        "generated_at": _iso_now(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run release-quality protected corridor validation.")
    parser.add_argument("--profile", action="append", choices=list(PROFILES), help="profile(s) to run (defaults to all)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output artifact path")
    parser.add_argument("--check-prereqs", action="store_true", help="verify protected corridor environment prerequisites and exit")
    parser.add_argument("--bootstrap", action="store_true", help="attempt deterministic dependency bootstrap before running corridor")
    args = parser.parse_args(list(argv) if argv is not None else None)

    selected_profiles = args.profile or list(PROFILES)
    if args.bootstrap:
        ok, bootstrap_output = bootstrap_prerequisites()
        if not ok:
            print(json.dumps({"bootstrap": "failed", "output_excerpt": " | ".join(bootstrap_output.splitlines()[:3])}, sort_keys=True))
            return 2

    prereq_status = check_prerequisites()
    if args.check_prereqs:
        print(json.dumps(asdict(prereq_status), sort_keys=True))
        return 0 if prereq_status.ready else 2

    report = run_validation(profiles=selected_profiles, output_path=Path(args.output), prerequisite_status=prereq_status)
    print(json.dumps({"output": str(Path(args.output)), "profile_count": len(selected_profiles)}, sort_keys=True))
    if not prereq_status.ready:
        return 2
    any_blocking = any(profile["summary"]["blocking_failure_count"] > 0 for profile in report["profiles"])
    any_provisioning = any(profile["summary"]["provisioning_failure_count"] > 0 for profile in report["profiles"])
    any_policy_skip = any(profile["summary"]["policy_skip_count"] > 0 for profile in report["profiles"])
    if any_provisioning:
        return 2
    if any_policy_skip:
        return 3
    return 1 if any_blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
