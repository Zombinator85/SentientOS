from __future__ import annotations

from pathlib import Path

from sentientos.diagnostics import (
    DiagnosticErrorFrame,
    ErrorClass,
    FailedPhase,
    RECOVERY_FAILED,
    RECOVERY_SKIPPED,
    RECOVERY_SUCCEEDED,
    RecoveryProofArtifact,
    attempt_recovery,
    build_error_frame,
)
from sentientos.diagnostics.recovery import RecoveryPlan, RecoveryResult


def _install_missing_dir_frame(missing_path: Path) -> DiagnosticErrorFrame:
    return build_error_frame(
        error_code="MISSING_RESOURCE",
        error_class=ErrorClass.INSTALL,
        failed_phase=FailedPhase.INSTALL,
        suppressed_actions=["retry"],
        human_summary="Install workspace directory is missing.",
        technical_details={"missing_path": missing_path.as_posix(), "missing_kind": "directory"},
    )


def test_recovery_success_path(tmp_path: Path) -> None:
    missing_dir = tmp_path / "logs" / "install_workspace"
    frame = _install_missing_dir_frame(missing_dir)

    outcome = attempt_recovery(frame)

    assert outcome.status == RECOVERY_SUCCEEDED
    assert missing_dir.exists()
    assert outcome.proof is not None
    assert outcome.proof.verification_passed is True
    assert outcome.recovered_frame is not None
    assert outcome.recovered_frame.status == "RECOVERED"


def test_recovery_failed_path(tmp_path: Path) -> None:
    blocking_file = tmp_path / "blocked"
    blocking_file.write_text("not a directory", encoding="utf-8")
    missing_dir = blocking_file / "install_workspace"
    frame = _install_missing_dir_frame(missing_dir)

    outcome = attempt_recovery(frame)

    assert outcome.status == RECOVERY_FAILED
    assert outcome.proof is None
    assert not missing_dir.exists()


def test_recovery_proof_determinism() -> None:
    proof_one = RecoveryProofArtifact.build(
        error_code="MISSING_RESOURCE",
        ladder_id="install-missing-directory-v1",
        pre_snapshot_hash="pre",
        post_snapshot_hash="post",
        verification_passed=True,
    )
    proof_two = RecoveryProofArtifact.build(
        error_code="MISSING_RESOURCE",
        ladder_id="install-missing-directory-v1",
        pre_snapshot_hash="pre",
        post_snapshot_hash="post",
        verification_passed=True,
    )
    assert proof_one.recovery_id == proof_two.recovery_id


def test_recovery_invariant_recheck(tmp_path: Path) -> None:
    missing_dir = tmp_path / "logs" / "install_workspace"
    frame = _install_missing_dir_frame(missing_dir)

    outcome = attempt_recovery(frame)

    assert outcome.status == RECOVERY_SUCCEEDED
    assert outcome.proof is not None
    assert outcome.proof.verification_passed is True


def test_recovery_no_retry(tmp_path: Path) -> None:
    class FailingLadder:
        ladder_id = "test-ladder"
        applicable_error_codes = ("MISSING_RESOURCE",)

        def __init__(self) -> None:
            self.execute_calls = 0

        def preconditions(self, _frame: DiagnosticErrorFrame) -> bool:
            return True

        def simulate(self, frame: DiagnosticErrorFrame) -> RecoveryPlan:
            missing_path = Path(frame.technical_details["missing_path"])
            return RecoveryPlan(
                ladder_id=self.ladder_id,
                error_code=frame.error_code,
                missing_path=missing_path,
                pre_snapshot_hash="pre",
            )

        def execute(self, plan: RecoveryPlan) -> RecoveryResult:
            self.execute_calls += 1
            return RecoveryResult(success=False, post_snapshot_hash=plan.pre_snapshot_hash)

        def verify(self) -> bool:
            return False

        def summarize(self, plan: RecoveryPlan) -> str:
            return f"Test recovery summary for {plan.missing_path}"

    missing_dir = tmp_path / "logs" / "install_workspace"
    frame = _install_missing_dir_frame(missing_dir)
    ladder = FailingLadder()

    outcome = attempt_recovery(frame, registry={"MISSING_RESOURCE": ladder})

    assert outcome.status == RECOVERY_FAILED
    assert ladder.execute_calls == 1


def test_recovery_idempotent_second_run(tmp_path: Path) -> None:
    missing_dir = tmp_path / "logs" / "install_workspace"
    frame = _install_missing_dir_frame(missing_dir)

    first = attempt_recovery(frame)
    second = attempt_recovery(frame)

    assert first.status == RECOVERY_SUCCEEDED
    assert second.status == RECOVERY_SKIPPED
