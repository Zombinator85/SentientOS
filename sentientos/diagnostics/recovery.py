"""Deterministic recovery ladders for install-time diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Protocol
import re

import sys

from sentientos.capability_registry import (
    capability_snapshot_hash,
    disable_capability,
    is_capability_disabled,
)
from sentientos.introspection.spine import EventType, emit_introspection_event
from sentientos.optional_deps import optional_dependency_for_module

from .error_frame import ErrorClass, FailedPhase, build_error_frame
from .error_frame import DiagnosticErrorFrame
from .recovery_eligibility import RecoveryEligibility
from .recovery_eligibility import RECOVERY_ELIGIBILITY_REGISTRY


RECOVERY_SUCCEEDED = "RECOVERY_SUCCEEDED"
RECOVERY_FAILED = "RECOVERY_FAILED"
RECOVERY_SKIPPED = "RECOVERY_SKIPPED"
INTEGRITY_VIOLATION_RECOVERY_RECURSION = "INTEGRITY_VIOLATION_RECOVERY_RECURSION"
ACK_REQUIRED_LADDER_ALLOWLIST: tuple[str, ...] = ()
LADDER_DOCSTRING_SECTIONS = ("Scope:", "Excluded domains:", "Safety rationale:")
_ERROR_CODE_PATTERN = re.compile(r"^[A-Z0-9_]+$")


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
    """Scope: Install-time creation of missing workspace directories.
    Excluded domains: File deletion, file content mutation, permission escalation.
    Safety rationale: Only creates a verified missing directory for an INSTALL error frame.
    """

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
    """Scope: CLI/install/import optional dependency isolation for missing modules.
    Excluded domains: Protected capabilities (cognition, integrity, forgetting, recovery).
    Safety rationale: Disables only optional, non-protected capabilities when an import is absent.
    """

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


def _unique_ladders(registry: Mapping[str, RecoveryLadder]) -> tuple[RecoveryLadder, ...]:
    seen: set[int] = set()
    ladders: list[RecoveryLadder] = []
    for ladder in registry.values():
        ladder_id = id(ladder)
        if ladder_id in seen:
            continue
        seen.add(ladder_id)
        ladders.append(ladder)
    return tuple(ladders)


def ladder_error_code_map(
    registry: Mapping[str, RecoveryLadder] = RecoveryLadderRegistry,
) -> dict[str, tuple[RecoveryLadder, ...]]:
    coverage: dict[str, list[RecoveryLadder]] = {}
    for ladder in _unique_ladders(registry):
        codes = ladder.applicable_error_codes
        for code in codes:
            coverage.setdefault(code, []).append(ladder)
    return {code: tuple(ladders) for code, ladders in coverage.items()}


def validate_recovery_ladders(
    *,
    registry: Mapping[str, RecoveryLadder] = RecoveryLadderRegistry,
    eligibility_registry: Mapping[str, tuple[RecoveryEligibility, str]] = RECOVERY_ELIGIBILITY_REGISTRY,
    ack_required_allowlist: tuple[str, ...] = ACK_REQUIRED_LADDER_ALLOWLIST,
) -> None:
    errors: list[str] = []
    coverage = ladder_error_code_map(registry)
    seen_ladder_ids: set[str] = set()

    for ladder in _unique_ladders(registry):
        if not isinstance(ladder.ladder_id, str) or not ladder.ladder_id:
            errors.append("Recovery ladder missing ladder_id.")
        elif ladder.ladder_id in seen_ladder_ids:
            errors.append(f"Duplicate ladder_id detected: {ladder.ladder_id}")
        else:
            seen_ladder_ids.add(ladder.ladder_id)

        codes = ladder.applicable_error_codes
        if not isinstance(codes, tuple) or not codes:
            errors.append(f"Ladder {ladder.ladder_id} must declare a tuple of applicable_error_codes.")
            continue
        for code in codes:
            if not isinstance(code, str) or not code:
                errors.append(f"Ladder {ladder.ladder_id} has invalid error_code entry.")
                continue
            if _ERROR_CODE_PATTERN.fullmatch(code) is None:
                errors.append(
                    f"Ladder {ladder.ladder_id} uses non-explicit error_code pattern: {code}"
                )
            if code not in eligibility_registry:
                errors.append(f"Ladder {ladder.ladder_id} references unknown error_code {code}.")
            if registry.get(code) is not ladder:
                errors.append(
                    f"Ladder {ladder.ladder_id} not explicitly registered for error_code {code}."
                )

    for code, ladders in coverage.items():
        if len(ladders) > 1:
            ladder_ids = ", ".join(sorted({ladder.ladder_id for ladder in ladders}))
            errors.append(f"Multiple ladders claim error_code {code}: {ladder_ids}")

    for code, (eligibility, _reason) in eligibility_registry.items():
        ladders = coverage.get(code, ())
        if eligibility == RecoveryEligibility.NEVER_RECOVER and ladders:
            errors.append(f"NEVER_RECOVER error_code {code} has a ladder assignment.")
        if eligibility == RecoveryEligibility.ACK_REQUIRED and ladders and code not in ack_required_allowlist:
            errors.append(f"ACK_REQUIRED error_code {code} must be explicitly whitelisted.")

    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"Recovery ladder validation failed:\n{joined}")


def validate_ladder_docstrings(
    ladders: Iterable[RecoveryLadder],
    *,
    required_sections: tuple[str, ...] = LADDER_DOCSTRING_SECTIONS,
) -> tuple[str, ...]:
    issues: list[str] = []
    for ladder in ladders:
        docstring = ladder.__class__.__doc__ or ""
        missing = [section for section in required_sections if section not in docstring]
        if missing:
            missing_text = ", ".join(missing)
            issues.append(f"{ladder.ladder_id} missing docstring sections: {missing_text}")
    return tuple(issues)


def _is_recovery_recursion_input(frame: DiagnosticErrorFrame) -> bool:
    return frame.status == "RECOVERED" or frame.recovery_reference is not None


def _recovery_recursion_violation_frame(frame: DiagnosticErrorFrame) -> DiagnosticErrorFrame:
    return build_error_frame(
        error_code="INVARIANT_VIOLATION",
        error_class=ErrorClass.INTEGRITY,
        failed_phase=frame.failed_phase,
        violated_invariant=INTEGRITY_VIOLATION_RECOVERY_RECURSION,
        suppressed_actions=["auto_recovery", "retry"],
        human_summary="Automatic recovery recursion detected; recovery halted.",
        technical_details={
            "status": frame.status,
            "error_code": frame.error_code,
            "recovery_reference": frame.recovery_reference,
        },
        caused_by=frame,
        recovery_eligibility=RecoveryEligibility.NEVER_RECOVER,
        eligibility_reason="RECOVERY_RECURSION_BLOCKED",
    )


def _violates_recovery_depth_invariant(frame: DiagnosticErrorFrame) -> bool:
    return frame.recoverable or frame.recovery_eligibility == RecoveryEligibility.RECOVERABLE


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
        recoverable=False,
        recovery_reference=proof.recovery_id,
        recovery_eligibility=RecoveryEligibility.NEVER_RECOVER,
        eligibility_reason="RECOVERY_RECURSION_BLOCKED",
    )


def attempt_recovery(
    frame: DiagnosticErrorFrame,
    *,
    registry: Mapping[str, RecoveryLadder] = RecoveryLadderRegistry,
) -> RecoveryOutcome:
    if _is_recovery_recursion_input(frame):
        _emit_recovery_event(
            frame,
            status="refused",
            reason="recovery_recursion_blocked",
        )
        return RecoveryOutcome(
            status=RECOVERY_FAILED,
            recovered_frame=_recovery_recursion_violation_frame(frame),
            proof=None,
        )
    if frame.recovery_eligibility != RecoveryEligibility.RECOVERABLE:
        _emit_recovery_event(
            frame,
            status="refused",
            reason="recovery_ineligible",
        )
        return RecoveryOutcome(status=RECOVERY_SKIPPED, recovered_frame=None, proof=None)

    ladder = registry.get(frame.error_code)
    if ladder is None or not ladder.preconditions(frame):
        _emit_recovery_event(
            frame,
            status="refused",
            reason="ladder_unavailable" if ladder is None else "preconditions_failed",
            ladder_id=getattr(ladder, "ladder_id", None),
        )
        return RecoveryOutcome(status=RECOVERY_SKIPPED, recovered_frame=None, proof=None)

    plan = ladder.simulate(frame)
    _emit_recovery_simulation(frame, ladder, plan)
    result = ladder.execute(plan)
    if not result.success:
        _emit_recovery_event(
            frame,
            status="failed",
            reason="execution_failed",
            ladder_id=plan.ladder_id,
            pre_snapshot_hash=plan.pre_snapshot_hash,
            post_snapshot_hash=result.post_snapshot_hash,
        )
        return RecoveryOutcome(status=RECOVERY_FAILED, recovered_frame=None, proof=None)

    verified = ladder.verify()
    if not verified:
        _emit_recovery_event(
            frame,
            status="failed",
            reason="verification_failed",
            ladder_id=plan.ladder_id,
            pre_snapshot_hash=plan.pre_snapshot_hash,
            post_snapshot_hash=result.post_snapshot_hash,
        )
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
    if _violates_recovery_depth_invariant(recovered_frame):
        _emit_recovery_event(
            frame,
            status="failed",
            reason="recovery_depth_violation",
            ladder_id=plan.ladder_id,
            pre_snapshot_hash=plan.pre_snapshot_hash,
            post_snapshot_hash=result.post_snapshot_hash,
        )
        return RecoveryOutcome(
            status=RECOVERY_FAILED,
            recovered_frame=_recovery_recursion_violation_frame(recovered_frame),
            proof=None,
        )
    _emit_recovery_event(
        frame,
        status="executed",
        reason="recovery_verified",
        ladder_id=plan.ladder_id,
        pre_snapshot_hash=plan.pre_snapshot_hash,
        post_snapshot_hash=result.post_snapshot_hash,
    )
    return RecoveryOutcome(status=RECOVERY_SUCCEEDED, recovered_frame=recovered_frame, proof=proof)


def _emit_recovery_simulation(
    frame: DiagnosticErrorFrame,
    ladder: RecoveryLadder,
    plan: RecoveryPlan | OptionalModuleIsolationPlan,
) -> None:
    metadata = {
        "error_code": frame.error_code,
        "ladder_id": ladder.ladder_id,
        "pre_snapshot_hash": getattr(plan, "pre_snapshot_hash", None),
        "missing_module": getattr(plan, "missing_module", None),
        "capability": getattr(plan, "capability", None),
    }
    emit_introspection_event(
        event_type=EventType.RECOVERY_SIMULATION,
        phase=frame.failed_phase.value.lower(),
        summary="Recovery ladder simulated.",
        metadata=metadata,
        linked_artifact_ids=[frame.content_hash()],
    )


def _emit_recovery_event(
    frame: DiagnosticErrorFrame,
    *,
    status: str,
    reason: str,
    ladder_id: str | None = None,
    pre_snapshot_hash: str | None = None,
    post_snapshot_hash: str | None = None,
) -> None:
    metadata = {
        "error_code": frame.error_code,
        "ladder_id": ladder_id,
        "status": status,
        "reason": reason,
        "pre_snapshot_hash": pre_snapshot_hash,
        "post_snapshot_hash": post_snapshot_hash,
    }
    emit_introspection_event(
        event_type=EventType.RECOVERY_EXECUTION,
        phase=frame.failed_phase.value.lower(),
        summary="Recovery ladder outcome recorded.",
        metadata=metadata,
        linked_artifact_ids=[frame.content_hash()],
    )


validate_recovery_ladders()
