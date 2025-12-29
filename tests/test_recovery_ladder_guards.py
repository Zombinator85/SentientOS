from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.diagnostics import (
    DiagnosticErrorFrame,
    ErrorClass,
    FailedPhase,
    RECOVERY_FAILED,
    RECOVERY_SUCCEEDED,
    RecoveryEligibility,
    attempt_recovery,
    build_error_frame,
)
from sentientos.diagnostics.recovery import (
    ACK_REQUIRED_LADDER_ALLOWLIST,
    INTEGRITY_VIOLATION_RECOVERY_RECURSION,
    RecoveryLadderRegistry,
    ladder_error_code_map,
    validate_ladder_docstrings,
    validate_recovery_ladders,
)
from sentientos.diagnostics.recovery_eligibility import RECOVERY_ELIGIBILITY_REGISTRY


class _BaseTestLadder:
    ladder_id = "TEST_LADDER"
    applicable_error_codes = ("MISSING_RESOURCE",)

    def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
        return True

    def simulate(self, _frame: DiagnosticErrorFrame):
        raise NotImplementedError

    def execute(self, _plan):
        raise NotImplementedError

    def verify(self) -> bool:
        return False

    def summarize(self, _plan) -> str:
        return "test"


def _unique_ladders():
    return list(dict.fromkeys(RecoveryLadderRegistry.values()))


def _install_missing_dir_frame(missing_path: Path) -> DiagnosticErrorFrame:
    return build_error_frame(
        error_code="MISSING_RESOURCE",
        error_class=ErrorClass.INSTALL,
        failed_phase=FailedPhase.INSTALL,
        suppressed_actions=["retry"],
        human_summary="Install workspace directory is missing.",
        technical_details={"missing_path": missing_path.as_posix(), "missing_kind": "directory"},
    )


def test_ladder_exhaustiveness_and_eligibility_guardrails() -> None:
    coverage = ladder_error_code_map()
    for error_code, (eligibility, _reason) in RECOVERY_ELIGIBILITY_REGISTRY.items():
        ladders = coverage.get(error_code, ())
        if eligibility == RecoveryEligibility.RECOVERABLE:
            assert len(ladders) <= 1
        if eligibility == RecoveryEligibility.NEVER_RECOVER:
            assert not ladders
        if eligibility == RecoveryEligibility.ACK_REQUIRED and error_code not in ACK_REQUIRED_LADDER_ALLOWLIST:
            assert not ladders


def test_ladder_overlap_detection() -> None:
    class LadderA(_BaseTestLadder):
        ladder_id = "LADDER_A"
        applicable_error_codes = ("MISSING_RESOURCE",)

    class LadderB(_BaseTestLadder):
        ladder_id = "LADDER_B"
        applicable_error_codes = ("MISSING_RESOURCE",)

    registry = {
        "MISSING_RESOURCE": LadderA(),
        "CLI_IMPORT_MODULE_MISSING": LadderB(),
    }

    with pytest.raises(ValueError, match="Multiple ladders claim error_code"):
        validate_recovery_ladders(registry=registry)


def test_ladder_registry_consistency_rejection() -> None:
    class LadderA(_BaseTestLadder):
        ladder_id = "LADDER_A"
        applicable_error_codes = ("CLI_IMPORT_MODULE_MISSING",)

    registry = {"MISSING_RESOURCE": LadderA()}

    with pytest.raises(ValueError, match="not explicitly registered"):
        validate_recovery_ladders(registry=registry)


def test_ladder_ack_required_rejection() -> None:
    class LadderA(_BaseTestLadder):
        ladder_id = "LADDER_A"
        applicable_error_codes = ("PERMISSION_DENIED",)

    registry = {"PERMISSION_DENIED": LadderA()}

    with pytest.raises(ValueError, match="ACK_REQUIRED error_code"):
        validate_recovery_ladders(registry=registry)


def test_ladder_pattern_rejection() -> None:
    class LadderA(_BaseTestLadder):
        ladder_id = "LADDER_A"
        applicable_error_codes = ("IMPORT_*",)

    registry = {"IMPORT_*": LadderA()}

    with pytest.raises(ValueError, match="non-explicit error_code pattern"):
        validate_recovery_ladders(registry=registry)


def test_ladder_docstring_sections_present() -> None:
    issues = validate_ladder_docstrings(_unique_ladders())
    assert issues == ()


def test_ladder_docstring_missing_sections() -> None:
    class LadderA(_BaseTestLadder):
        """Scope: test ladder only."""

        ladder_id = "LADDER_A"
        applicable_error_codes = ("MISSING_RESOURCE",)

    issues = validate_ladder_docstrings([LadderA()])
    assert issues


def test_recovery_recursion_prevention(tmp_path: Path) -> None:
    missing_dir = tmp_path / "logs" / "install_workspace"
    frame = _install_missing_dir_frame(missing_dir)

    outcome = attempt_recovery(frame)

    assert outcome.status == RECOVERY_SUCCEEDED
    assert outcome.recovered_frame is not None
    assert outcome.recovered_frame.recovery_eligibility == RecoveryEligibility.NEVER_RECOVER
    assert outcome.recovered_frame.recoverable is False

    recursion = attempt_recovery(outcome.recovered_frame)
    assert recursion.status == RECOVERY_FAILED
    assert recursion.recovered_frame is not None
    assert recursion.recovered_frame.violated_invariant == INTEGRITY_VIOLATION_RECOVERY_RECURSION
