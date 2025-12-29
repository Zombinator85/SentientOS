"""Deterministic recovery ladders for install-time diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping, Protocol

from .error_frame import DiagnosticErrorFrame
from .recovery_eligibility import RecoveryEligibility


RECOVERY_SUCCEEDED = "RECOVERY_SUCCEEDED"
RECOVERY_FAILED = "RECOVERY_FAILED"
RECOVERY_SKIPPED = "RECOVERY_SKIPPED"


def _snapshot_hash(path: Path) -> str:
    payload = json.dumps(
        {
            "path": path.as_posix(),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
        },
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RecoveryPlan:
    ladder_id: str
    error_code: str
    missing_path: Path
    pre_snapshot_hash: str


@dataclass(frozen=True)
class RecoveryResult:
    success: bool
    post_snapshot_hash: str


@dataclass(frozen=True)
class RecoveryProofArtifact:
    recovery_id: str
    error_code: str
    ladder_id: str
    pre_snapshot_hash: str
    post_snapshot_hash: str
    verification_passed: bool

    def to_json(self) -> str:
        return json.dumps(
            {
                "recovery_id": self.recovery_id,
                "error_code": self.error_code,
                "ladder_id": self.ladder_id,
                "pre_snapshot_hash": self.pre_snapshot_hash,
                "post_snapshot_hash": self.post_snapshot_hash,
                "verification_passed": self.verification_passed,
            },
            separators=(",", ":"),
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def build(
        *,
        error_code: str,
        ladder_id: str,
        pre_snapshot_hash: str,
        post_snapshot_hash: str,
        verification_passed: bool,
    ) -> "RecoveryProofArtifact":
        payload = json.dumps(
            {
                "error_code": error_code,
                "ladder_id": ladder_id,
                "pre_snapshot_hash": pre_snapshot_hash,
                "post_snapshot_hash": post_snapshot_hash,
                "verification_passed": verification_passed,
            },
            separators=(",", ":"),
            ensure_ascii=False,
            sort_keys=True,
        )
        recovery_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return RecoveryProofArtifact(
            recovery_id=recovery_id,
            error_code=error_code,
            ladder_id=ladder_id,
            pre_snapshot_hash=pre_snapshot_hash,
            post_snapshot_hash=post_snapshot_hash,
            verification_passed=verification_passed,
        )


@dataclass(frozen=True)
class RecoveryOutcome:
    status: str
    recovered_frame: DiagnosticErrorFrame | None
    proof: RecoveryProofArtifact | None


class RecoveryLadder(Protocol):
    ladder_id: str
    applicable_error_codes: tuple[str, ...]

    def preconditions(self, frame: DiagnosticErrorFrame) -> bool:
        ...

    def simulate(self, frame: DiagnosticErrorFrame) -> RecoveryPlan:
        ...

    def execute(self, plan: RecoveryPlan) -> RecoveryResult:
        ...

    def verify(self) -> bool:
        ...


class MissingInstallDirectoryRecoveryLadder:
    ladder_id = "install-missing-directory-v1"
    applicable_error_codes = ("MISSING_RESOURCE",)

    def __init__(self) -> None:
        self._last_plan: RecoveryPlan | None = None

    def preconditions(self, frame: DiagnosticErrorFrame) -> bool:
        missing_path = frame.technical_details.get("missing_path")
        missing_kind = frame.technical_details.get("missing_kind")
        return (
            frame.failed_phase.value == "INSTALL"
            and frame.status == "ERROR"
            and frame.recovery_eligibility == RecoveryEligibility.RECOVERABLE
            and frame.error_code in self.applicable_error_codes
            and missing_kind == "directory"
            and isinstance(missing_path, str)
            and bool(missing_path)
            and not Path(missing_path).exists()
        )

    def simulate(self, frame: DiagnosticErrorFrame) -> RecoveryPlan:
        missing_path = Path(str(frame.technical_details.get("missing_path")))
        pre_snapshot_hash = _snapshot_hash(missing_path)
        return RecoveryPlan(
            ladder_id=self.ladder_id,
            error_code=frame.error_code,
            missing_path=missing_path,
            pre_snapshot_hash=pre_snapshot_hash,
        )

    def execute(self, plan: RecoveryPlan) -> RecoveryResult:
        self._last_plan = plan
        try:
            plan.missing_path.mkdir(parents=True, exist_ok=False)
            return RecoveryResult(success=True, post_snapshot_hash=_snapshot_hash(plan.missing_path))
        except Exception:
            return RecoveryResult(success=False, post_snapshot_hash=_snapshot_hash(plan.missing_path))

    def verify(self) -> bool:
        if self._last_plan is None:
            return False
        path = self._last_plan.missing_path
        return path.exists() and path.is_dir()


RecoveryLadderRegistry: Mapping[str, RecoveryLadder] = {
    "MISSING_RESOURCE": MissingInstallDirectoryRecoveryLadder()
}


def persist_recovery_proof(
    proof: RecoveryProofArtifact, *, path: str = "logs/install_recovery_proofs.jsonl"
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(proof.to_json())
        handle.write("\n")


def promote_recovered_frame(
    frame: DiagnosticErrorFrame,
    *,
    proof: RecoveryProofArtifact,
    summary: str,
) -> DiagnosticErrorFrame:
    return DiagnosticErrorFrame(
        schema_version=frame.schema_version,
        status="RECOVERED",
        error_code=frame.error_code,
        error_class=frame.error_class,
        failed_phase=frame.failed_phase,
        violated_invariant=frame.violated_invariant,
        system_snapshot_hash=frame.system_snapshot_hash,
        cognitive_snapshot_hash=frame.cognitive_snapshot_hash,
        suppressed_actions=list(frame.suppressed_actions),
        human_summary=summary,
        technical_details=frame.technical_details,
        caused_by=frame,
        timestamp_logical=frame.timestamp_logical,
        recoverable=frame.recoverable,
        recovery_reference=proof.recovery_id,
        recovery_eligibility=frame.recovery_eligibility,
        eligibility_reason=frame.eligibility_reason,
    )


def attempt_recovery(
    frame: DiagnosticErrorFrame,
    *,
    registry: Mapping[str, RecoveryLadder] = RecoveryLadderRegistry,
) -> RecoveryOutcome:
    if frame.recovery_eligibility != RecoveryEligibility.RECOVERABLE:
        return RecoveryOutcome(status=RECOVERY_SKIPPED, recovered_frame=None, proof=None)

    ladder = registry.get(frame.error_code)
    if ladder is None or not ladder.preconditions(frame):
        return RecoveryOutcome(status=RECOVERY_SKIPPED, recovered_frame=None, proof=None)

    plan = ladder.simulate(frame)
    result = ladder.execute(plan)
    if not result.success:
        return RecoveryOutcome(status=RECOVERY_FAILED, recovered_frame=None, proof=None)

    verified = ladder.verify()
    if not verified:
        return RecoveryOutcome(status=RECOVERY_FAILED, recovered_frame=None, proof=None)

    proof = RecoveryProofArtifact.build(
        error_code=frame.error_code,
        ladder_id=plan.ladder_id,
        pre_snapshot_hash=plan.pre_snapshot_hash,
        post_snapshot_hash=result.post_snapshot_hash,
        verification_passed=verified,
    )
    recovered_frame = promote_recovered_frame(
        frame,
        proof=proof,
        summary=f"Recovered by creating missing directory {plan.missing_path}.",
    )
    return RecoveryOutcome(status=RECOVERY_SUCCEEDED, recovered_frame=recovered_frame, proof=proof)
