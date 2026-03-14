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


def test_run_validation_writes_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(protected_corridor, "_iso_now", lambda: "2026-01-01T00:00:00Z")

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
    assert payload["profiles"][0]["profile"] == "ci-advisory"
    assert payload["profiles"][0]["deferred_debt"][0]["name"] == "mypy_protected_scope"
