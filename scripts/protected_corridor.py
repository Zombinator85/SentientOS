from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

PROFILES = ("local-dev-relaxed", "ci-advisory", "federation-enforce")
DEFAULT_OUTPUT = Path("glow/contracts/protected_corridor_report.json")


@dataclass(frozen=True)
class CorridorCheck:
    name: str
    command: tuple[str, ...]
    blocking: bool
    expected_relaxed: str
    notes: str


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
    ),
    CorridorCheck(
        name="operator_cli_targeted",
        command=("python", "-m", "scripts.run_tests", "-q", "tests/test_operator_cli_hygiene.py", "sentientos/tests/test_ops_cli.py"),
        blocking=True,
        expected_relaxed="pass",
        notes="Operator/CLI visibility and hygiene checks.",
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
    if returncode != 0 and expected == "pass":
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
    non_blocking_failures = [asdict(item) for item in results if item.bucket in {"legacy_deferred_debt", "non_blocking_optional_historical_runtime_state"}]
    passed = [asdict(item) for item in results if item.bucket == "pass"]

    health = "green"
    if blocking_failures:
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
            "non_blocking_failure_count": len(non_blocking_failures),
            "repo_health": health,
        },
        "blocking_failures": blocking_failures,
        "non_blocking_failures": non_blocking_failures,
        "deferred_debt": [entry for entry in non_blocking_failures if entry["bucket"] == "legacy_deferred_debt"],
    }


def run_validation(*, profiles: Sequence[str], output_path: Path) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "protected_corridor": {
            "definition": [
                {
                    "name": check.name,
                    "command": list(check.command),
                    "blocking": check.blocking,
                    "notes": check.notes,
                }
                for check in CHECKS
            ]
        },
        "profiles": [run_profile(profile) for profile in profiles],
        "generated_at": _iso_now(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run release-quality protected corridor validation.")
    parser.add_argument("--profile", action="append", choices=list(PROFILES), help="profile(s) to run (defaults to all)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output artifact path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    selected_profiles = args.profile or list(PROFILES)
    report = run_validation(profiles=selected_profiles, output_path=Path(args.output))
    print(json.dumps({"output": str(Path(args.output)), "profile_count": len(selected_profiles)}, sort_keys=True))
    any_blocking = any(profile["summary"]["blocking_failure_count"] > 0 for profile in report["profiles"])
    return 1 if any_blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
