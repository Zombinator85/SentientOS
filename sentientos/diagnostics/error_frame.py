"""Structured diagnostic error artifacts for SentientOS."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from collections import OrderedDict
from typing import Any, Mapping, Optional
import traceback

from .recovery_eligibility import RecoveryEligibility, get_recovery_eligibility

class ErrorClass(str, Enum):
    INSTALL = "INSTALL"
    CONFIG = "CONFIG"
    IMPORT = "IMPORT"
    INTEGRITY = "INTEGRITY"
    EXECUTION = "EXECUTION"
    TEST = "TEST"
    ENVIRONMENT = "ENVIRONMENT"
    INTERNAL = "INTERNAL"


class FailedPhase(str, Enum):
    INSTALL = "INSTALL"
    BOOT = "BOOT"
    IMPORT = "IMPORT"
    CLI = "CLI"
    CYCLE = "CYCLE"
    COMMIT = "COMMIT"
    TEST = "TEST"


class LogicalClock:
    """Deterministic logical clock for timestamping diagnostic frames."""

    def __init__(self) -> None:
        self._counter = 0

    def tick(self) -> int:
        self._counter += 1
        return self._counter

    def reset(self) -> None:
        self._counter = 0


_DEFAULT_CLOCK = LogicalClock()


_SENSITIVE_KEYS = ("password", "secret", "token", "key", "credential", "auth")


def _redact_mapping(value: Mapping[str, Any]) -> dict:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if any(marker in key.lower() for marker in _SENSITIVE_KEYS):
            sanitized[key] = "***"
        else:
            sanitized[key] = _redact_value(item)
    return sanitized


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def sanitize_technical_details(details: Mapping[str, Any]) -> dict:
    return _redact_mapping(details)


def _traceback_excerpt(exc: BaseException) -> list[str]:
    tb = traceback.TracebackException.from_exception(exc, capture_locals=False)
    return list(tb.format())


@dataclass(frozen=True)
class DiagnosticErrorFrame:
    schema_version: int
    status: str
    error_code: str
    error_class: ErrorClass
    failed_phase: FailedPhase
    violated_invariant: Optional[str]
    system_snapshot_hash: Optional[str]
    cognitive_snapshot_hash: Optional[str]
    suppressed_actions: list[str]
    human_summary: str
    technical_details: Mapping[str, Any]
    caused_by: Optional["DiagnosticErrorFrame"]
    timestamp_logical: int
    recoverable: bool = False
    recovery_reference: Optional[str] = None
    recovery_eligibility: RecoveryEligibility = RecoveryEligibility.NEVER_RECOVER
    eligibility_reason: str = "UNKNOWN_ERROR_CODE"

    def to_ordered_dict(self) -> OrderedDict:
        ordered = OrderedDict(
            [
                ("schema_version", self.schema_version),
                ("status", self.status),
                ("error_code", self.error_code),
                ("error_class", self.error_class.value),
                ("failed_phase", self.failed_phase.value),
                ("violated_invariant", self.violated_invariant),
                ("system_snapshot_hash", self.system_snapshot_hash),
                ("cognitive_snapshot_hash", self.cognitive_snapshot_hash),
                ("suppressed_actions", list(self.suppressed_actions)),
                ("human_summary", self.human_summary),
                ("technical_details", sanitize_technical_details(self.technical_details)),
                (
                    "caused_by",
                    self.caused_by.to_ordered_dict() if self.caused_by is not None else None,
                ),
                ("timestamp_logical", self.timestamp_logical),
                ("recoverable", self.recoverable),
                ("recovery_reference", self.recovery_reference),
                ("recovery_eligibility", self.recovery_eligibility.value),
                ("eligibility_reason", self.eligibility_reason),
            ]
        )
        return ordered

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_ordered_dict(), indent=indent, ensure_ascii=False)

    def content_hash(self) -> str:
        payload = json.dumps(
            self.to_ordered_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DiagnosticError(Exception):
    """Exception wrapper carrying a diagnostic error frame."""

    def __init__(self, frame: DiagnosticErrorFrame) -> None:
        super().__init__(frame.human_summary)
        self.frame = frame


def build_error_frame(
    *,
    error_code: str,
    error_class: ErrorClass,
    failed_phase: FailedPhase,
    violated_invariant: Optional[str] = None,
    system_snapshot_hash: Optional[str] = None,
    cognitive_snapshot_hash: Optional[str] = None,
    suppressed_actions: Optional[list[str]] = None,
    human_summary: str,
    technical_details: Optional[Mapping[str, Any]] = None,
    caused_by: Optional[DiagnosticErrorFrame] = None,
    timestamp_logical: Optional[int] = None,
    recoverable: bool = False,
    recovery_reference: Optional[str] = None,
    recovery_eligibility: Optional[RecoveryEligibility] = None,
    eligibility_reason: Optional[str] = None,
    status: str = "ERROR",
    clock: Optional[LogicalClock] = None,
) -> DiagnosticErrorFrame:
    details = technical_details or {}
    effective_clock = clock or _DEFAULT_CLOCK
    logical_time = timestamp_logical if timestamp_logical is not None else effective_clock.tick()
    registry_eligibility, registry_reason = get_recovery_eligibility(error_code)
    resolved_eligibility = recovery_eligibility or registry_eligibility
    resolved_reason = eligibility_reason or registry_reason
    return DiagnosticErrorFrame(
        schema_version=1,
        status=status,
        error_code=error_code,
        error_class=error_class,
        failed_phase=failed_phase,
        violated_invariant=violated_invariant,
        system_snapshot_hash=system_snapshot_hash,
        cognitive_snapshot_hash=cognitive_snapshot_hash,
        suppressed_actions=list(suppressed_actions or []),
        human_summary=human_summary,
        technical_details=sanitize_technical_details(details),
        caused_by=caused_by,
        timestamp_logical=logical_time,
        recoverable=recoverable,
        recovery_reference=recovery_reference,
        recovery_eligibility=resolved_eligibility,
        eligibility_reason=resolved_reason,
    )


def _default_error_code(error_class: ErrorClass, failed_phase: FailedPhase, exc: BaseException) -> str:
    if isinstance(exc, ModuleNotFoundError):
        if failed_phase == FailedPhase.CLI:
            return "CLI_IMPORT_MODULE_MISSING"
        if failed_phase == FailedPhase.TEST:
            return "TEST_IMPORT_SURFACE_VIOLATION"
        return "IMPORT_MODULE_MISSING"
    if isinstance(exc, AssertionError):
        return "INVARIANT_VIOLATION"
    if isinstance(exc, FileNotFoundError):
        return "MISSING_RESOURCE"
    if isinstance(exc, PermissionError):
        return "PERMISSION_DENIED"
    if isinstance(exc, ImportError):
        if failed_phase == FailedPhase.TEST:
            return "TEST_IMPORT_SURFACE_VIOLATION"
        return "IMPORT_FAILURE"
    return f"{error_class.value}_UNHANDLED"


def _default_error_class(exc: BaseException, failed_phase: FailedPhase) -> ErrorClass:
    if isinstance(exc, ModuleNotFoundError):
        return ErrorClass.TEST if failed_phase == FailedPhase.TEST else ErrorClass.IMPORT
    if isinstance(exc, ImportError):
        return ErrorClass.TEST if failed_phase == FailedPhase.TEST else ErrorClass.IMPORT
    if isinstance(exc, AssertionError):
        return ErrorClass.INTEGRITY
    if isinstance(exc, FileNotFoundError):
        return ErrorClass.INSTALL
    if isinstance(exc, PermissionError):
        return ErrorClass.ENVIRONMENT
    return ErrorClass.EXECUTION


def frame_exception(
    exc: BaseException,
    *,
    failed_phase: FailedPhase,
    error_code: Optional[str] = None,
    error_class: Optional[ErrorClass] = None,
    violated_invariant: Optional[str] = None,
    system_snapshot_hash: Optional[str] = None,
    cognitive_snapshot_hash: Optional[str] = None,
    suppressed_actions: Optional[list[str]] = None,
    human_summary: Optional[str] = None,
    technical_details: Optional[Mapping[str, Any]] = None,
    caused_by: Optional[DiagnosticErrorFrame] = None,
    clock: Optional[LogicalClock] = None,
) -> DiagnosticErrorFrame:
    if isinstance(exc, DiagnosticError):
        return exc.frame
    resolved_class = error_class or _default_error_class(exc, failed_phase)
    resolved_code = error_code or _default_error_code(resolved_class, failed_phase, exc)
    summary = human_summary or f"{type(exc).__name__}: {exc}"
    details = {
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback": _traceback_excerpt(exc),
    }
    if isinstance(exc, ModuleNotFoundError):
        details["missing_module"] = exc.name
    if isinstance(exc, FileNotFoundError):
        details["missing_path"] = getattr(exc, "filename", None)
    if technical_details:
        details.update(technical_details)
    return build_error_frame(
        error_code=resolved_code,
        error_class=resolved_class,
        failed_phase=failed_phase,
        violated_invariant=violated_invariant,
        system_snapshot_hash=system_snapshot_hash,
        cognitive_snapshot_hash=cognitive_snapshot_hash,
        suppressed_actions=suppressed_actions,
        human_summary=summary,
        technical_details=details,
        caused_by=caused_by,
        clock=clock,
    )


def persist_error_frame(frame: DiagnosticErrorFrame, *, path: str = "logs/install_diagnostics.jsonl") -> None:
    from pathlib import Path

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(frame.to_json())
        handle.write("\n")
