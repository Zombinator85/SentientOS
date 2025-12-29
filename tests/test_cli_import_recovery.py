from __future__ import annotations

import argparse
import sys

from sentientos import __main__ as sentientos_main
from sentientos.capability_registry import (
    disabled_capabilities,
    is_capability_disabled,
    reset_capability_registry,
)
from sentientos.diagnostics import (
    DiagnosticErrorFrame,
    ErrorClass,
    FailedPhase,
    RECOVERY_SKIPPED,
    RECOVERY_SUCCEEDED,
    RecoveryProofArtifact,
    attempt_recovery,
    build_error_frame,
)
from sentientos.optional_deps import (
    OPTIONAL_DEPENDENCIES,
    OptionalDependency,
    reset_optional_dependency_state,
)


def _register_optional_dependency(entry: OptionalDependency) -> None:
    OPTIONAL_DEPENDENCIES[entry.package] = entry
    reset_optional_dependency_state()


def _build_cli_missing_module_frame(module_name: str) -> DiagnosticErrorFrame:
    return build_error_frame(
        error_code="CLI_IMPORT_MODULE_MISSING",
        error_class=ErrorClass.IMPORT,
        failed_phase=FailedPhase.CLI,
        suppressed_actions=["auto_recovery", "retry", "state_mutation"],
        human_summary=f"ModuleNotFoundError: {module_name}",
        technical_details={"missing_module": module_name},
    )


def test_optional_import_recovery_success(monkeypatch) -> None:
    reset_capability_registry()
    reset_optional_dependency_state()
    sys.modules.pop("optional_test_module", None)
    entry = OptionalDependency(
        package="optional-test",
        module_name="optional_test_module",
        features=("optional_feature",),
        import_probe=lambda: None,
        install_hint="pip install optional-test",
    )
    monkeypatch.setitem(OPTIONAL_DEPENDENCIES, entry.package, entry)

    frame = _build_cli_missing_module_frame("optional_test_module")
    outcome = attempt_recovery(frame)

    assert outcome.status == RECOVERY_SUCCEEDED
    assert is_capability_disabled("optional_feature")
    assert outcome.proof is not None
    assert outcome.proof.missing_module == "optional_test_module"
    assert outcome.proof.disabled_capability == "optional_feature"
    assert outcome.recovered_frame is not None
    assert (
        outcome.recovered_frame.human_summary
        == "Recovered by disabling optional capability ‹optional_feature› due to missing module ‹optional_test_module›."
    )


def test_optional_import_recovery_refused_for_required(monkeypatch) -> None:
    reset_capability_registry()
    reset_optional_dependency_state()
    entry = OptionalDependency(
        package="required-test",
        module_name="required_test_module",
        features=("required_feature",),
        import_probe=lambda: None,
        install_hint="pip install required-test",
        missing_behavior="hard_fail",
    )
    monkeypatch.setitem(OPTIONAL_DEPENDENCIES, entry.package, entry)

    frame = _build_cli_missing_module_frame("required_test_module")
    outcome = attempt_recovery(frame)

    assert outcome.status == RECOVERY_SKIPPED
    assert not is_capability_disabled("required_feature")


def test_optional_import_recovery_idempotent(monkeypatch) -> None:
    reset_capability_registry()
    reset_optional_dependency_state()
    entry = OptionalDependency(
        package="optional-test",
        module_name="optional_test_module",
        features=("optional_feature",),
        import_probe=lambda: None,
        install_hint="pip install optional-test",
    )
    monkeypatch.setitem(OPTIONAL_DEPENDENCIES, entry.package, entry)

    frame = _build_cli_missing_module_frame("optional_test_module")
    first = attempt_recovery(frame)
    second = attempt_recovery(frame)

    assert first.status == RECOVERY_SUCCEEDED
    assert second.status == RECOVERY_SKIPPED


def test_optional_recovery_proof_determinism() -> None:
    proof_one = RecoveryProofArtifact.build(
        error_code="CLI_IMPORT_MODULE_MISSING",
        ladder_id="CLI_IMPORT_OPTIONAL_MODULE_ISOLATION",
        pre_snapshot_hash="pre",
        post_snapshot_hash="post",
        verification_passed=True,
        missing_module="optional_test_module",
        disabled_capability="optional_feature",
    )
    proof_two = RecoveryProofArtifact.build(
        error_code="CLI_IMPORT_MODULE_MISSING",
        ladder_id="CLI_IMPORT_OPTIONAL_MODULE_ISOLATION",
        pre_snapshot_hash="pre",
        post_snapshot_hash="post",
        verification_passed=True,
        missing_module="optional_test_module",
        disabled_capability="optional_feature",
    )
    assert proof_one.recovery_id == proof_two.recovery_id


def test_optional_recovery_isolates_capability(monkeypatch) -> None:
    reset_capability_registry()
    reset_optional_dependency_state()
    entry = OptionalDependency(
        package="optional-test",
        module_name="optional_test_module",
        features=("optional_feature",),
        import_probe=lambda: None,
        install_hint="pip install optional-test",
    )
    monkeypatch.setitem(OPTIONAL_DEPENDENCIES, entry.package, entry)

    frame = _build_cli_missing_module_frame("optional_test_module")
    outcome = attempt_recovery(frame)

    assert outcome.status == RECOVERY_SUCCEEDED
    assert "optional_feature" in disabled_capabilities()
    assert "other_feature" not in disabled_capabilities()


def test_no_recover_bypass(monkeypatch) -> None:
    reset_capability_registry()
    reset_optional_dependency_state()
    entry = OptionalDependency(
        package="optional-test",
        module_name="optional_test_module",
        features=("optional_feature",),
        import_probe=lambda: None,
        install_hint="pip install optional-test",
    )
    monkeypatch.setitem(OPTIONAL_DEPENDENCIES, entry.package, entry)
    frame = _build_cli_missing_module_frame("optional_test_module")
    args = argparse.Namespace(no_recover=True)

    outcome = sentientos_main._maybe_attempt_recovery(frame, args)

    assert outcome is None
    assert not is_capability_disabled("optional_feature")


def test_cli_optional_dependency_message(capsys) -> None:
    sentientos_main._emit_optional_dependency_notice(
        capability="optional_feature",
        module="optional_test_module",
    )
    captured = capsys.readouterr()
    assert "Optional capability ‹optional_feature› disabled due to missing dependency ‹optional_test_module›." in captured.out
    assert "Install ‹optional_test_module› to re-enable ‹optional_feature›." in captured.out
