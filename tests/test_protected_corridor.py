from __future__ import annotations

import json
from pathlib import Path

from scripts import protected_corridor


def test_classification_is_deterministic_for_non_blocking_audit_warning() -> None:
    check = next(item for item in protected_corridor.CHECKS if item.name == "verify_audits_strict")
    first = protected_corridor.classify_result(check, profile="ci-advisory", returncode=1, output='{"audit_chain_status":"broken"}')
    second = protected_corridor.classify_result(check, profile="ci-advisory", returncode=1, output='{"audit_chain_status":"broken"}')

    assert first == second
    assert first.bucket == "non_blocking_optional_historical_runtime_state"
    assert first.blocking is False


def test_profile_aware_expectation_for_forge_status() -> None:
    check = next(item for item in protected_corridor.CHECKS if item.name == "forge_status")

    relaxed = protected_corridor.classify_result(check, profile="local-dev-relaxed", returncode=3, output="")
    strict = protected_corridor.classify_result(check, profile="federation-enforce", returncode=3, output="")

    assert relaxed.expected_in_profile == "warn"
    assert relaxed.bucket == "blocking_release_corridor_failure"
    assert strict.expected_in_profile == "pass"
    assert strict.bucket == "blocking_release_corridor_failure"


def test_classifies_unprovisioned_environment() -> None:
    check = next(item for item in protected_corridor.CHECKS if item.name == "contract_status_rollup_targeted")

    result = protected_corridor.classify_result(
        check,
        profile="ci-advisory",
        returncode=1,
        output="run_tests import airlock failed: fastapi import failed: No module named 'fastapi'",
    )

    assert result.bucket == "environment_unprovisioned"


def test_classifies_policy_doctrine_skip() -> None:
    check = next(item for item in protected_corridor.CHECKS if item.name == "contract_status_rollup_targeted")

    result = protected_corridor.classify_result(
        check,
        profile="ci-advisory",
        returncode=1,
        output="CI proof requires executed tests. Collection/info modes are not admissible.",
    )

    assert result.bucket == "policy_doctrine_skipped"


def test_run_validation_writes_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(protected_corridor, "_iso_now", lambda: "2026-01-01T00:00:00Z")
    monkeypatch.setattr(
        protected_corridor,
        "check_prerequisites",
        lambda *args, **kwargs: protected_corridor.PrerequisiteStatus(ready=True, checks={}, diagnostics=[]),
    )

    outcomes = {
        tuple(check.command): 0 for check in protected_corridor.CHECKS
    }
    outcomes[tuple(next(check.command for check in protected_corridor.CHECKS if check.name == "mypy_protected_scope"))] = 1

    def fake_run(command: tuple[str, ...], env: dict[str, str]) -> tuple[int, str]:
        return outcomes[tuple(command)], ""

    monkeypatch.setattr(protected_corridor, "_run_command", fake_run)

    output = tmp_path / "corridor.json"
    report = protected_corridor.run_validation(profiles=["ci-advisory"], output_path=output)

    assert report["profiles"][0]["summary"]["blocking_failure_count"] == 0
    assert report["profiles"][0]["summary"]["non_blocking_failure_count"] == 1
    assert output.exists()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provisioning"]["ready"] is True
    assert payload["profiles"][0]["profile"] == "ci-advisory"
    assert payload["profiles"][0]["deferred_debt"][0]["name"] == "mypy_protected_scope"
    assert payload["global_summary"]["status"] == "amber"
    assert payload["global_summary"]["debt_profiles"] == ["ci-advisory"]


def test_run_validation_skips_profiles_when_unprovisioned(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(protected_corridor, "_iso_now", lambda: "2026-01-01T00:00:00Z")
    monkeypatch.setattr(
        protected_corridor,
        "check_prerequisites",
        lambda *args, **kwargs: protected_corridor.PrerequisiteStatus(
            ready=False,
            checks={"contract_status_rollup_targeted": ["editable_install"]},
            diagnostics=["editable_install: editable install check failed (distribution-not-found)"],
        ),
    )

    output = tmp_path / "corridor_unready.json"
    report = protected_corridor.run_validation(profiles=["ci-advisory"], output_path=output)

    assert report["profiles"] == []
    assert report["provisioning"]["ready"] is False
    assert "contract_status_rollup_targeted" in report["provisioning"]["check_missing_prerequisites"]




def test_check_prerequisites_reports_missing_dependencies(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        protected_corridor,
        "get_editable_install_status",
        lambda repo_root: type("Status", (), {"ok": False, "reason": "distribution-not-found"})(),
    )
    monkeypatch.setattr(
        protected_corridor,
        "_test_runtime_imports_ok",
        lambda repo_root: (False, ["fastapi import failed: No module named 'fastapi'"]),
    )

    status = protected_corridor.check_prerequisites(repo_root=tmp_path)

    assert status.ready is False
    assert "contract_status_rollup_targeted" in status.checks
    assert "editable_install" in status.checks["contract_status_rollup_targeted"]
    assert "test_runtime_imports" in status.checks["contract_status_rollup_targeted"]
    assert any("distribution-not-found" in message for message in status.diagnostics)


def test_contract_status_rollup_surface_is_in_protected_corridor() -> None:
    check = next(item for item in protected_corridor.CHECKS if item.name == "contract_status_rollup_targeted")

    assert check.blocking is True
    assert check.prerequisites == ("editable_install", "test_runtime_imports")
    assert check.command == ("python", "-m", "scripts.run_tests", "-q", "tests/test_contract_status_rollup.py")


def test_classifies_missing_command_as_environment_unavailable() -> None:
    check = next(item for item in protected_corridor.CHECKS if item.name == "contract_status")
    result = protected_corridor.classify_result(
        check,
        profile="ci-advisory",
        returncode=127,
        output="command unavailable in environment: [Errno 2] No such file or directory: 'python'",
    )
    assert result.bucket == "command_unavailable_in_environment"
