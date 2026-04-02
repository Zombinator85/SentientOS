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
from sentientos.protected_mutation_corridor import (
    classify_touched_paths,
    corridor_definition,
    discover_touched_paths,
    non_bypass_model_definition,
)

PROFILES = ("local-dev-relaxed", "ci-advisory", "federation-enforce")
DEFAULT_OUTPUT = Path("glow/contracts/protected_corridor_report.json")
INSTALL_EXTRAS = ".[dev,test]"
CORRIDOR_VERSION = "2026-04-02.1"

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
    relevance: dict[str, Any] | None = None


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
        name="protected_mutation_forward_enforcement",
        command=("python", "scripts/verify_kernel_admission_provenance.py", "--mode", "forward-enforcement", "--summary-only"),
        blocking=True,
        expected_relaxed="pass",
        notes="Forward-enforcement for currently covered protected-mutation surfaces blocks fresh regressions without turning legacy debt into a global blocker.",
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
    try:
        completed = subprocess.run(command, capture_output=True, text=True, env=env)
    except FileNotFoundError as exc:
        return 127, f"command unavailable in environment: {exc}"
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


def classify_result(
    check: CorridorCheck,
    *,
    profile: str,
    returncode: int,
    output: str,
    protected_mutation_relevance: dict[str, Any] | None = None,
) -> CheckResult:
    expected = _expected_for_profile(check, profile)
    outcome = "pass" if returncode == 0 else "warn"
    relevance_payload: dict[str, Any] | None = None
    if check.name == "protected_mutation_forward_enforcement":
        summary: dict[str, Any] = {}
        try:
            parsed = json.loads(output) if output.strip() else {}
            if isinstance(parsed, dict):
                summary = parsed
        except json.JSONDecodeError:
            summary = {}
        is_relevant = bool((protected_mutation_relevance or {}).get("intersects_corridor", False))
        mode = str(summary.get("mode") or "forward-enforcement")
        overall = str(summary.get("overall_status") or "unknown")
        if overall == "current_violation_present":
            proof_status = "forward_violation_present" if mode == "forward-enforcement" else "strict_violation_present"
        elif overall == "legacy_only":
            proof_status = "legacy_only"
        elif overall == "healthy":
            proof_status = "forward_clean"
        else:
            proof_status = "unknown"
        if not is_relevant:
            proof_status = "not_applicable"
        relevance_payload = {
            "corridor_intersects_change_surface": is_relevant,
            "implicated_domains": list((protected_mutation_relevance or {}).get("implicated_domains", [])),
            "forward_enforcement_relevant": is_relevant,
            "forward_enforcement_ran": True,
            "forward_enforcement_status": proof_status,
            "verifier_overall_status": overall,
            "protected_intent": summary.get("protected_intent", {}),
            "protected_intent_status_counts": summary.get("counts", {}).get("intent_status_classification", {}),
            "execution_consistency": summary.get("execution_consistency", {}),
            "non_bypass": summary.get("non_bypass", {}),
            "fresh_bypass_candidate_present": bool(
                (summary.get("non_bypass") or {}).get("fresh_violation_count", 0)
            ),
            "bypass_blocking_in_mode": bool(
                (summary.get("non_bypass") or {}).get("fresh_violation_blocking_in_mode", False)
            ),
        }
        if not is_relevant:
            note = "Forward-enforcement remains visible but is non-blocking when touched paths do not intersect the covered protected-mutation corridor."
            return CheckResult(
                name=check.name,
                command=check.command,
                returncode=returncode,
                outcome="warn" if returncode != 0 else "pass",
                bucket="corridor_not_applicable",
                blocking=False,
                expected_in_profile=expected,
                note=note,
                output_excerpt=" | ".join([line.strip() for line in output.splitlines() if line.strip()][:3]),
                relevance=relevance_payload,
            )

    if returncode != 0 and "command unavailable in environment" in output:
        bucket = "command_unavailable_in_environment"
    elif returncode != 0 and (
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
    elif returncode != 0 and expected == "warn":
        bucket = "advisory_mismatch_or_expected_warning"
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
        relevance=relevance_payload,
    )


def run_profile(
    profile: str,
    *,
    checks: Sequence[CorridorCheck] = CHECKS,
    protected_mutation_relevance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["SENTIENTOS_ENFORCEMENT_PROFILE"] = profile
    env.setdefault("PYTHONPATH", ".")

    results: list[CheckResult] = []
    for check in checks:
        rc, output = _run_command(check.command, env)
        results.append(
            classify_result(
                check,
                profile=profile,
                returncode=rc,
                output=output,
                protected_mutation_relevance=protected_mutation_relevance,
            )
        )

    blocking_failures = [asdict(item) for item in results if item.bucket.startswith("blocking_")]
    provisioning_failures = [asdict(item) for item in results if item.bucket == "environment_unprovisioned"]
    unavailable_commands = [asdict(item) for item in results if item.bucket == "command_unavailable_in_environment"]
    doctrine_skips = [asdict(item) for item in results if item.bucket == "policy_doctrine_skipped"]
    advisory_warnings = [asdict(item) for item in results if item.bucket == "advisory_mismatch_or_expected_warning"]
    non_blocking_failures = [asdict(item) for item in results if item.bucket in {"legacy_deferred_debt", "non_blocking_optional_historical_runtime_state"}]
    not_applicable = [asdict(item) for item in results if item.bucket == "corridor_not_applicable"]
    passed = [asdict(item) for item in results if item.bucket == "pass"]

    health = "green"
    if blocking_failures or provisioning_failures or unavailable_commands:
        health = "red"
    elif non_blocking_failures or advisory_warnings or doctrine_skips or not_applicable:
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
            "command_unavailable_count": len(unavailable_commands),
            "policy_skip_count": len(doctrine_skips),
            "advisory_warning_count": len(advisory_warnings),
            "non_blocking_failure_count": len(non_blocking_failures),
            "not_applicable_count": len(not_applicable),
            "repo_health": health,
        },
        "blocking_failures": blocking_failures,
        "provisioning_failures": provisioning_failures,
        "command_unavailable": unavailable_commands,
        "policy_skips": doctrine_skips,
        "advisory_warnings": advisory_warnings,
        "non_blocking_failures": non_blocking_failures,
        "not_applicable": not_applicable,
        "deferred_debt": [entry for entry in non_blocking_failures if entry["bucket"] == "legacy_deferred_debt"],
    }


def _global_summary(profiles: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not profiles:
        return {
            "status": "provisioning_required",
            "repo_health": "red",
            "blocking_profiles": [],
            "advisory_profiles": [],
            "debt_profiles": [],
            "not_applicable_profiles": [],
            "corridor_blocking": True,
        }

    blocking_profiles: list[str] = []
    advisory_profiles: list[str] = []
    debt_profiles: list[str] = []
    not_applicable_profiles: list[str] = []
    deferred_debt: dict[str, dict[str, Any]] = {}
    protected_mutation_status: dict[str, str] = {}
    protected_intent_status_by_profile: dict[str, dict[str, int]] = {}
    for profile in profiles:
        summary = profile.get("summary") if isinstance(profile, dict) else {}
        profile_name = str(profile.get("profile"))
        if int(summary.get("blocking_failure_count", 0)) > 0:
            blocking_profiles.append(profile_name)
        if int(summary.get("provisioning_failure_count", 0)) > 0 or int(summary.get("command_unavailable_count", 0)) > 0:
            blocking_profiles.append(profile_name)
        if int(summary.get("policy_skip_count", 0)) > 0 or int(summary.get("advisory_warning_count", 0)) > 0:
            advisory_profiles.append(profile_name)
        if int(summary.get("non_blocking_failure_count", 0)) > 0:
            debt_profiles.append(profile_name)
            for check in profile.get("deferred_debt", []):
                if not isinstance(check, dict):
                    continue
                name = check.get("name")
                if not isinstance(name, str):
                    continue
                deferred_debt.setdefault(
                    name,
                    {
                        "name": name,
                        "bucket": check.get("bucket"),
                        "note": check.get("note"),
                        "profiles": [],
                    },
                )
                deferred_debt[name]["profiles"].append(profile_name)
        if int(summary.get("not_applicable_count", 0)) > 0:
            not_applicable_profiles.append(profile_name)
        for check in profile.get("checks", []):
            if not isinstance(check, dict) or check.get("name") != "protected_mutation_forward_enforcement":
                continue
            relevance = check.get("relevance")
            if isinstance(relevance, dict):
                state = relevance.get("forward_enforcement_status")
                if isinstance(state, str):
                    protected_mutation_status[profile_name] = state
                status_counts = relevance.get("protected_intent_status_counts")
                if isinstance(status_counts, dict):
                    protected_intent_status_by_profile[profile_name] = {
                        str(key): int(value)
                        for key, value in status_counts.items()
                        if isinstance(key, str) and isinstance(value, int)
                    }

    blocking_profiles = sorted(set(blocking_profiles))
    advisory_profiles = sorted(set(advisory_profiles))
    debt_profiles = sorted(set(debt_profiles))
    not_applicable_profiles = sorted(set(not_applicable_profiles))
    if blocking_profiles:
        status = "red"
        repo_health = "red"
    elif debt_profiles or advisory_profiles:
        status = "amber"
        repo_health = "amber"
    else:
        status = "green"
        repo_health = "green"

    return {
        "status": status,
        "repo_health": repo_health,
        "blocking_profiles": blocking_profiles,
        "advisory_profiles": advisory_profiles,
        "debt_profiles": debt_profiles,
        "not_applicable_profiles": not_applicable_profiles,
        "corridor_blocking": bool(blocking_profiles),
        "deferred_debt_outside_corridor": sorted(deferred_debt.values(), key=lambda item: item["name"]),
        "protected_mutation_forward_enforcement_status_by_profile": protected_mutation_status,
        "protected_intent_status_by_profile": protected_intent_status_by_profile,
    }


def run_validation(
    *,
    profiles: Sequence[str],
    output_path: Path,
    prerequisite_status: PrerequisiteStatus | None = None,
    touched_paths: Sequence[str] | None = None,
    diff_base: str | None = None,
) -> dict[str, Any]:
    status = prerequisite_status or check_prerequisites()
    touched = discover_touched_paths(repo_root=Path("."), diff_base=diff_base, explicit_paths=touched_paths)
    corridor_relevance = classify_touched_paths(touched.get("paths", [])) if isinstance(touched.get("paths"), list) else classify_touched_paths([])
    profile_reports = (
        [run_profile(profile, protected_mutation_relevance=corridor_relevance) for profile in profiles] if status.ready else []
    )
    report = {
        "schema_version": 1,
        "corridor_version": CORRIDOR_VERSION,
        "provisioning": {
            "ready": status.ready,
            "check_missing_prerequisites": status.checks,
            "diagnostics": status.diagnostics,
            "prerequisite_labels": PREREQUISITE_LABELS,
        },
        "protected_corridor": {
            "version": CORRIDOR_VERSION,
            "definition": [
                {
                    "name": check.name,
                    "command": list(check.command),
                    "blocking": check.blocking,
                    "notes": check.notes,
                    "prerequisites": list(check.prerequisites),
                }
                for check in CHECKS
            ],
            "failure_taxonomy": [
                "blocking_release_corridor_failure",
                "blocking_correctness_failure",
                "advisory_mismatch_or_expected_warning",
                "environment_unprovisioned",
                "non_blocking_optional_historical_runtime_state",
                "legacy_deferred_debt",
                "corridor_not_applicable",
                "audit_chain_local_state_outside_corridor",
                "command_unavailable_in_environment",
            ],
        },
        "covered_protected_mutation_corridor": corridor_definition(),
        "covered_protected_mutation_corridor_non_bypass_model": non_bypass_model_definition(),
        "corridor_relevance": {
            **corridor_relevance,
            "path_discovery": touched,
            "forward_enforcement_relevant": bool(corridor_relevance.get("intersects_corridor", False)),
            "status_vocabulary": [
                "not_applicable",
                "legacy_only",
                "forward_clean",
                "forward_violation_present",
                "strict_violation_present",
                "declared_and_consistent",
                "declared_but_mismatched",
                "undeclared_but_protected_action",
                "declared_but_not_applicable",
                "no_obvious_bypass_detected",
                "alternate_writer_detected",
                "unadmitted_operator_path_detected",
                "uncovered_mutation_entrypoint_detected",
                "canonical_boundary_missing",
            ],
        },
        "profiles": profile_reports,
        "global_summary": _global_summary(profile_reports),
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
    parser.add_argument("--diff-base", default=None, help="optional git diff base for touched-path corridor relevance")
    parser.add_argument("--touched-path", action="append", default=None, help="explicit touched path for corridor relevance (repeatable)")
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

    report = run_validation(
        profiles=selected_profiles,
        output_path=Path(args.output),
        prerequisite_status=prereq_status,
        touched_paths=args.touched_path,
        diff_base=args.diff_base,
    )
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
