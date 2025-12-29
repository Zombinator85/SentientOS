"""Recovery eligibility registry for diagnostic error codes."""

from __future__ import annotations

from collections import OrderedDict
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping


class RecoveryEligibility(str, Enum):
    RECOVERABLE = "RECOVERABLE"
    ACK_REQUIRED = "ACK_REQUIRED"
    NEVER_RECOVER = "NEVER_RECOVER"


ERROR_CODE_CATALOG: tuple[str, ...] = (
    "CLI_APPROVAL_REQUIRED",
    "CLI_IMPORT_MODULE_MISSING",
    "IMPORT_MODULE_MISSING",
    "TEST_IMPORT_SURFACE_VIOLATION",
    "INVARIANT_VIOLATION",
    "MISSING_RESOURCE",
    "PERMISSION_DENIED",
    "IMPORT_FAILURE",
    "INSTALL_UNHANDLED",
    "CONFIG_UNHANDLED",
    "IMPORT_UNHANDLED",
    "INTEGRITY_UNHANDLED",
    "EXECUTION_UNHANDLED",
    "TEST_UNHANDLED",
    "ENVIRONMENT_UNHANDLED",
    "INTERNAL_UNHANDLED",
)


RECOVERY_ELIGIBILITY_ENTRIES: tuple[tuple[str, RecoveryEligibility, str], ...] = (
    ("CLI_APPROVAL_REQUIRED", RecoveryEligibility.NEVER_RECOVER, "OPERATOR_APPROVAL_REQUIRED"),
    ("CLI_IMPORT_MODULE_MISSING", RecoveryEligibility.RECOVERABLE, "OPTIONAL_IMPORT_MISSING"),
    ("IMPORT_MODULE_MISSING", RecoveryEligibility.RECOVERABLE, "IMPORT_DEPENDENCY_MISSING"),
    (
        "TEST_IMPORT_SURFACE_VIOLATION",
        RecoveryEligibility.ACK_REQUIRED,
        "TEST_SURFACE_INTEGRITY",
    ),
    ("INVARIANT_VIOLATION", RecoveryEligibility.NEVER_RECOVER, "INVARIANT_BREACH"),
    ("MISSING_RESOURCE", RecoveryEligibility.RECOVERABLE, "MISSING_RESOURCE"),
    ("PERMISSION_DENIED", RecoveryEligibility.ACK_REQUIRED, "PERMISSION_GATED"),
    ("IMPORT_FAILURE", RecoveryEligibility.ACK_REQUIRED, "IMPORT_FAILURE"),
    ("INSTALL_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
    ("CONFIG_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
    ("IMPORT_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
    ("INTEGRITY_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
    ("EXECUTION_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
    ("TEST_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
    ("ENVIRONMENT_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
    ("INTERNAL_UNHANDLED", RecoveryEligibility.NEVER_RECOVER, "UNHANDLED_FAILURE"),
)


RECOVERY_ELIGIBILITY_REGISTRY: Mapping[str, tuple[RecoveryEligibility, str]] = OrderedDict(
    (error_code, (eligibility, reason))
    for error_code, eligibility, reason in RECOVERY_ELIGIBILITY_ENTRIES
)

UNKNOWN_ELIGIBILITY: tuple[RecoveryEligibility, str] = (
    RecoveryEligibility.NEVER_RECOVER,
    "UNKNOWN_ERROR_CODE",
)


def get_recovery_eligibility(error_code: str) -> tuple[RecoveryEligibility, str]:
    return RECOVERY_ELIGIBILITY_REGISTRY.get(error_code, UNKNOWN_ELIGIBILITY)


def registry_error_codes() -> tuple[str, ...]:
    return tuple(RECOVERY_ELIGIBILITY_REGISTRY.keys())


def registry_hash() -> str:
    payload = json.dumps(
        [
            [code, eligibility.value, reason]
            for code, (eligibility, reason) in RECOVERY_ELIGIBILITY_REGISTRY.items()
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def format_recovery_eligibility(eligibility: RecoveryEligibility) -> str:
    if eligibility == RecoveryEligibility.RECOVERABLE:
        return "Automatic recovery: possible (not attempted)"
    if eligibility == RecoveryEligibility.ACK_REQUIRED:
        return "Automatic recovery: requires operator acknowledgment"
    return "Automatic recovery: never permitted"


def ensure_registry_complete(error_codes: Iterable[str]) -> tuple[str, ...]:
    missing = [code for code in error_codes if code not in RECOVERY_ELIGIBILITY_REGISTRY]
    return tuple(missing)
