"""Deterministic recovery ladders for install-time diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping, Protocol

import sys

from sentientos.capability_registry import (
    capability_snapshot_hash,
    disable_capability,
    is_capability_disabled,
)
from sentientos.optional_deps import optional_dependency_for_module

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
    missing_module: str | None = None
    disabled_capability: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "recovery_id": self.recovery_id,
                "error_code": self.error_code,
                "ladder_id": self.ladder_id,
                "pre_snapshot_hash": self.pre_snapshot_hash,
                "post_snapshot_hash": self.post_snapshot_hash,
                "verification_passed": self.verification_passed,
                "missing_module": self.missing_module,
                "disabled_capability": self.disabled_capability,
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
        missing_module: str | None = None,
        disabled_capability: str | None = None,
    ) -> "RecoveryProofArtifact":
        payload = json.dumps(
            {
                "error_code": error_code,
                "ladder_id": ladder_id,
                "pre_snapshot_hash": pre_snapshot_hash,
                "post_snapshot_hash": post_snapshot_hash,
                "verification_passed": verification_passed,
                "missing_module": missing_module,
                "disabled_capability": disabled_capability,
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
            missing_module=missing_module,
            disabled_capability=disabled_capability,
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

    def summarize(self, plan: RecoveryPlan) -> str:
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

    def summarize(self, plan: RecoveryPlan) -> str:
        return f"Recovered by creating missing directory {plan.missing_path}."


@dataclass(frozen=True)
class OptionalModuleIsolationPlan:
    ladder_id: str
    error_code: str
    missing_module: str
    capability: str
    reason: str
    suppressed_actions: tuple[str, ...]
    pre_snapshot_hash: str


class OptionalModuleIsolationRecoveryLadder:
    ladder_id = "CLI_IMPORT_OPTIONAL_MODULE_ISOLATION"
    applicable_error_codes = ("CLI_IMPORT_MODULE_MISSING",)
    _allowed_phases = {"CLI", "INSTALL", "IMPORT"}
    _protected_capabilities = {"cognition", "integrity", "forgetting", "recovery"}

    def __init__(self) -> None:
        self._last_plan: OptionalModuleIsolationPlan | None = None
        self._last_result: RecoveryResult | None = None

    def preconditions(self, frame: DiagnosticErrorFrame) -> bool:
        missing_module = frame.technical_details.get("missing_module")
        if (
            frame.status != "ERROR"
            or frame.error_code not in self.applicable_error_codes
            or frame.failed_phase.value not in self._allowed_phases
            or not isinstance(missing_module, str)
            or not missing_module
        ):
            return False
        dependency = optional_dependency_for_module(missing_module)
        if dependency is None or dependency.missing_behavior == "hard_fail":
            return False
        capability = sorted(dependency.features)[0]
        if capability in self._protected_capabilities:
            return False
        if is_capability_disabled(capability):
            return False
        return True

    def simulate(self, frame: DiagnosticErrorFrame) -> OptionalModuleIsolationPlan:
        missing_module = str(frame.technical_details.get("missing_module"))
        dependency = optional_dependency_for_module(missing_module)
        if dependency is None:
            raise ValueError(f"Optional dependency not registered for module '{missing_module}'")
        capability = sorted(dependency.features)[0]
        pre_snapshot_hash = capability_snapshot_hash()
        return OptionalModuleIsolationPlan(
            ladder_id=self.ladder_id,
            error_code=frame.error_code,
            missing_module=missing_module,
            capability=capability,
            reason=f"missing optional dependency '{missing_module}'",
            suppressed_actions=tuple(frame.suppressed_actions),
            pre_snapshot_hash=pre_snapshot_hash,
        )

    def execute(self, plan: OptionalModuleIsolationPlan) -> RecoveryResult:
        self._last_plan = plan
        success = disable_capability(plan.capability, reason=plan.reason)
        result = RecoveryResult(success=success, post_snapshot_hash=capability_snapshot_hash())
        self._last_result = result
        return result

    def verify(self) -> bool:
        if self._last_plan is None or self._last_result is None:
            return False
        if not is_capability_disabled(self._last_plan.capability):
            return False
        if self._last_plan.missing_module in sys.modules:
            return False
        return self._last_result.post_snapshot_hash == capability_snapshot_hash()

    def summarize(self, plan: OptionalModuleIsolationPlan) -> str:
        return (
            "Recovered by disabling optional capability "
            f"‹{plan.capability}› due to missing module ‹{plan.missing_module}›."
        )


RecoveryLadderRegistry: Mapping[str, RecoveryLadder] = {
    "MISSING_RESOURCE": MissingInstallDirectoryRecoveryLadder(),
    "CLI_IMPORT_MODULE_MISSING": OptionalModuleIsolationRecoveryLadder(),
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
        missing_module=getattr(plan, "missing_module", None),
        disabled_capability=getattr(plan, "capability", None),
    )
    recovered_frame = promote_recovered_frame(
        frame,
        proof=proof,
        summary=ladder.summarize(plan),
    )
    return RecoveryOutcome(status=RECOVERY_SUCCEEDED, recovered_frame=recovered_frame, proof=proof)
