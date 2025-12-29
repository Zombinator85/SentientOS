from __future__ import annotations

import argparse
import importlib.abc
from pathlib import Path
import sys
from typing import Optional

import pytest

from sentientos import __main__ as sentientos_main
from sentientos.diagnostics import (
    DiagnosticErrorFrame,
    ErrorClass,
    FailedPhase,
    RECOVERY_FAILED,
    RECOVERY_SKIPPED,
    RecoveryEligibility,
    RecoveryProofArtifact,
    attempt_recovery,
    build_error_frame,
)
from sentientos.diagnostics.recovery import (
    INTEGRITY_VIOLATION_RECOVERY_RECURSION,
    RecoveryPlan,
    RecoveryResult,
    validate_recovery_ladders,
)
from sentientos.diagnostics.recovery_eligibility import get_recovery_eligibility

pytestmark = pytest.mark.no_legacy_skip


class _PoisonFinder(importlib.abc.MetaPathFinder):
    def __init__(self, module_name: str) -> None:
        self._module_name = module_name

    def find_spec(self, fullname: str, path, target=None):  # type: ignore[override]
        if fullname == self._module_name:
            raise ModuleNotFoundError(f"poisoned import: {fullname}")
        return None


def _install_missing_dir_frame(
    missing_path: Path,
    *,
    status: str = "ERROR",
    recovery_reference: str | None = None,
    recovery_eligibility: RecoveryEligibility | None = None,
    recoverable: bool = False,
) -> DiagnosticErrorFrame:
    return build_error_frame(
        error_code="MISSING_RESOURCE",
        error_class=ErrorClass.INSTALL,
        failed_phase=FailedPhase.INSTALL,
        suppressed_actions=["retry"],
        human_summary="Install workspace directory is missing.",
        technical_details={"missing_path": missing_path.as_posix(), "missing_kind": "directory"},
        status=status,
        recovery_reference=recovery_reference,
        recovery_eligibility=recovery_eligibility,
        recoverable=recoverable,
    )


def _proof_is_valid(proof: RecoveryProofArtifact) -> bool:
    expected = RecoveryProofArtifact.build(
        error_code=proof.error_code,
        ladder_id=proof.ladder_id,
        pre_snapshot_hash=proof.pre_snapshot_hash,
        post_snapshot_hash=proof.post_snapshot_hash,
        verification_passed=proof.verification_passed,
        missing_module=proof.missing_module,
        disabled_capability=proof.disabled_capability,
    )
    return expected.recovery_id == proof.recovery_id


def test_recursive_recovery_attack_blocks_second_ladder(tmp_path: Path) -> None:
    class CountingLadder:
        ladder_id = "COUNTING_LADDER"
        applicable_error_codes = ("MISSING_RESOURCE",)

        def __init__(self) -> None:
            self.simulate_calls = 0
            self.execute_calls = 0

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, _frame: DiagnosticErrorFrame) -> RecoveryPlan:
            self.simulate_calls += 1
            missing_path = tmp_path / "never"
            return RecoveryPlan(
                ladder_id=self.ladder_id,
                error_code="MISSING_RESOURCE",
                missing_path=missing_path,
                pre_snapshot_hash="pre",
            )

        def execute(self, plan: RecoveryPlan) -> RecoveryResult:
            self.execute_calls += 1
            return RecoveryResult(success=True, post_snapshot_hash=plan.pre_snapshot_hash)

        def verify(self) -> bool:
            return True

        def summarize(self, _plan: RecoveryPlan) -> str:
            return "counted"

    missing_dir = tmp_path / "logs" / "install_workspace"
    frame = _install_missing_dir_frame(
        missing_dir,
        status="RECOVERED",
        recovery_reference="proof-id",
        recovery_eligibility=RecoveryEligibility.RECOVERABLE,
        recoverable=True,
    )
    ladder = CountingLadder()

    outcome = attempt_recovery(frame, registry={"MISSING_RESOURCE": ladder})

    assert outcome.status == RECOVERY_FAILED
    assert outcome.proof is None
    assert ladder.simulate_calls == 0
    assert ladder.execute_calls == 0
    assert outcome.recovered_frame is not None
    assert (
        outcome.recovered_frame.violated_invariant == INTEGRITY_VIOLATION_RECOVERY_RECURSION
    ), "recursion guard must surface integrity violation"


def test_eligibility_forgery_is_ignored_for_never_recover() -> None:
    frame = build_error_frame(
        error_code="INVARIANT_VIOLATION",
        error_class=ErrorClass.INTEGRITY,
        failed_phase=FailedPhase.TEST,
        suppressed_actions=["auto_recovery"],
        human_summary="forged eligibility",
        recovery_eligibility=RecoveryEligibility.RECOVERABLE,
        eligibility_reason="FORGED",
        recoverable=True,
    )
    registry_eligibility, _reason = get_recovery_eligibility("INVARIANT_VIOLATION")

    outcome = attempt_recovery(frame)

    assert registry_eligibility == RecoveryEligibility.NEVER_RECOVER
    assert outcome.status == RECOVERY_SKIPPED
    assert outcome.proof is None
    assert outcome.recovered_frame is None


def test_ladder_overreach_multiple_codes_rejected() -> None:
    class OverreachLadder:
        ladder_id = "OVERREACH"
        applicable_error_codes = ("MISSING_RESOURCE", "INVARIANT_VIOLATION")

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, _frame: DiagnosticErrorFrame) -> RecoveryPlan:
            raise NotImplementedError

        def execute(self, _plan: RecoveryPlan) -> RecoveryResult:
            raise NotImplementedError

        def verify(self) -> bool:
            return False

        def summarize(self, _plan: RecoveryPlan) -> str:
            return "overreach"

    ladder = OverreachLadder()
    registry = {
        "MISSING_RESOURCE": ladder,
        "INVARIANT_VIOLATION": ladder,
    }

    with pytest.raises(ValueError, match="NEVER_RECOVER error_code INVARIANT_VIOLATION"):
        validate_recovery_ladders(registry=registry)


def test_ladder_overreach_wildcard_rejected() -> None:
    class WildcardLadder:
        ladder_id = "WILDCARD"
        applicable_error_codes = ("IMPORT_*",)

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, _frame: DiagnosticErrorFrame) -> RecoveryPlan:
            raise NotImplementedError

        def execute(self, _plan: RecoveryPlan) -> RecoveryResult:
            raise NotImplementedError

        def verify(self) -> bool:
            return False

        def summarize(self, _plan: RecoveryPlan) -> str:
            return "wildcard"

    registry = {"IMPORT_*": WildcardLadder()}

    with pytest.raises(ValueError, match="non-explicit error_code pattern"):
        validate_recovery_ladders(registry=registry)


def test_ladder_overreach_duplicate_claims_rejected() -> None:
    class LadderA:
        ladder_id = "LADDER_A"
        applicable_error_codes = ("MISSING_RESOURCE",)

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, _frame: DiagnosticErrorFrame) -> RecoveryPlan:
            raise NotImplementedError

        def execute(self, _plan: RecoveryPlan) -> RecoveryResult:
            raise NotImplementedError

        def verify(self) -> bool:
            return False

        def summarize(self, _plan: RecoveryPlan) -> str:
            return "a"

    class LadderB(LadderA):
        ladder_id = "LADDER_B"

    registry = {
        "MISSING_RESOURCE": LadderA(),
        "CLI_IMPORT_MODULE_MISSING": LadderB(),
    }

    with pytest.raises(ValueError, match="Multiple ladders claim error_code MISSING_RESOURCE"):
        validate_recovery_ladders(registry=registry)


def test_proof_tampering_detected_by_hash_mismatch() -> None:
    proof = RecoveryProofArtifact.build(
        error_code="MISSING_RESOURCE",
        ladder_id="install-missing-directory-v1",
        pre_snapshot_hash="pre",
        post_snapshot_hash="post",
        verification_passed=True,
    )
    tampered = RecoveryProofArtifact(
        recovery_id=proof.recovery_id,
        error_code=proof.error_code,
        ladder_id=proof.ladder_id,
        pre_snapshot_hash="tampered-pre",
        post_snapshot_hash=proof.post_snapshot_hash,
        verification_passed=proof.verification_passed,
        missing_module=proof.missing_module,
        disabled_capability=proof.disabled_capability,
    )

    assert _proof_is_valid(proof)
    assert not _proof_is_valid(tampered), "tampered proofs must fail integrity checks"


def test_proof_rejected_when_verification_fails(tmp_path: Path) -> None:
    class TamperDetectLadder:
        ladder_id = "TAMPER_DETECT"
        applicable_error_codes = ("MISSING_RESOURCE",)

        def __init__(self) -> None:
            self.plan: Optional[RecoveryPlan] = None

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, _frame: DiagnosticErrorFrame) -> RecoveryPlan:
            missing_path = tmp_path / "logs" / "install_workspace"
            self.plan = RecoveryPlan(
                ladder_id=self.ladder_id,
                error_code="MISSING_RESOURCE",
                missing_path=missing_path,
                pre_snapshot_hash="pre",
            )
            return self.plan

        def execute(self, plan: RecoveryPlan) -> RecoveryResult:
            return RecoveryResult(success=True, post_snapshot_hash=plan.pre_snapshot_hash)

        def verify(self) -> bool:
            return False

        def summarize(self, _plan: RecoveryPlan) -> str:
            return "tamper"

    frame = _install_missing_dir_frame(tmp_path / "logs" / "install_workspace")
    outcome = attempt_recovery(frame, registry={"MISSING_RESOURCE": TamperDetectLadder()})

    assert outcome.status == RECOVERY_FAILED
    assert outcome.proof is None
    assert outcome.recovered_frame is None


def test_cli_no_recover_blocks_recovery(tmp_path: Path) -> None:
    frame = _install_missing_dir_frame(tmp_path / "logs" / "install_workspace")
    args = argparse.Namespace(no_recover=True)

    outcome = sentientos_main._maybe_attempt_recovery(frame, args)

    assert outcome is None


def test_cli_chain_recovery_refused_for_recovered_frame(tmp_path: Path) -> None:
    frame = _install_missing_dir_frame(tmp_path / "logs" / "install_workspace")
    first = attempt_recovery(frame)

    assert first.recovered_frame is not None

    outcome = sentientos_main._maybe_attempt_recovery(
        first.recovered_frame,
        argparse.Namespace(no_recover=False),
    )

    assert outcome is None


def test_import_poisoning_guard_does_not_crash_safe_command(capsys) -> None:
    poison_name = "poison_optional_module"
    finder = _PoisonFinder(poison_name)
    sys.meta_path.insert(0, finder)
    sys.modules.pop(poison_name, None)
    try:
        sentientos_main.main(["status"])
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop(poison_name, None)

    captured = capsys.readouterr()
    assert "Status: locked for privileged operations" in captured.out


def test_snapshot_drift_aborts_recovery(tmp_path: Path) -> None:
    class DriftLadder:
        ladder_id = "DRIFT"
        applicable_error_codes = ("MISSING_RESOURCE",)

        def __init__(self) -> None:
            self.mutated = False

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, _frame: DiagnosticErrorFrame) -> RecoveryPlan:
            missing_path = tmp_path / "logs" / "install_workspace"
            missing_path.parent.mkdir(parents=True, exist_ok=True)
            missing_path.write_text("drift", encoding="utf-8")
            self.mutated = True
            return RecoveryPlan(
                ladder_id=self.ladder_id,
                error_code="MISSING_RESOURCE",
                missing_path=missing_path,
                pre_snapshot_hash="pre",
            )

        def execute(self, _plan: RecoveryPlan) -> RecoveryResult:
            return RecoveryResult(success=True, post_snapshot_hash="post")

        def verify(self) -> bool:
            return not self.mutated

        def summarize(self, _plan: RecoveryPlan) -> str:
            return "drift"

    frame = _install_missing_dir_frame(tmp_path / "logs" / "install_workspace")
    outcome = attempt_recovery(frame, registry={"MISSING_RESOURCE": DriftLadder()})

    assert outcome.status == RECOVERY_FAILED
    assert outcome.proof is None


def test_snapshot_no_change_aborts_recovery(tmp_path: Path) -> None:
    class NoChangeLadder:
        ladder_id = "NO_CHANGE"
        applicable_error_codes = ("MISSING_RESOURCE",)

        def __init__(self) -> None:
            self.last_pre_hash: Optional[str] = None

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, _frame: DiagnosticErrorFrame) -> RecoveryPlan:
            self.last_pre_hash = "same"
            return RecoveryPlan(
                ladder_id=self.ladder_id,
                error_code="MISSING_RESOURCE",
                missing_path=tmp_path / "logs" / "install_workspace",
                pre_snapshot_hash="same",
            )

        def execute(self, _plan: RecoveryPlan) -> RecoveryResult:
            return RecoveryResult(success=True, post_snapshot_hash="same")

        def verify(self) -> bool:
            return False

        def summarize(self, _plan: RecoveryPlan) -> str:
            return "no-change"

    frame = _install_missing_dir_frame(tmp_path / "logs" / "install_workspace")
    outcome = attempt_recovery(frame, registry={"MISSING_RESOURCE": NoChangeLadder()})

    assert outcome.status == RECOVERY_FAILED
    assert outcome.proof is None
