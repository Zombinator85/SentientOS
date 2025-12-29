from sentientos.diagnostics import (
    ERROR_CODE_CATALOG,
    RECOVERY_ELIGIBILITY_REGISTRY,
    RecoveryEligibility,
    ErrorClass,
    FailedPhase,
    build_error_frame,
    get_recovery_eligibility,
    recovery_eligibility_registry_hash,
)
from sentientos.diagnostics.recovery_eligibility import ensure_registry_complete


def test_recovery_registry_complete():
    missing = ensure_registry_complete(ERROR_CODE_CATALOG)
    assert missing == ()
    assert set(ERROR_CODE_CATALOG) == set(RECOVERY_ELIGIBILITY_REGISTRY.keys())


def test_unknown_codes_default_to_never_recover():
    eligibility, reason = get_recovery_eligibility("UNKNOWN_ERROR_CODE")
    assert eligibility == RecoveryEligibility.NEVER_RECOVER
    assert reason == "UNKNOWN_ERROR_CODE"


def test_invariant_errors_never_recover():
    eligibility, _reason = get_recovery_eligibility("INVARIANT_VIOLATION")
    assert eligibility == RecoveryEligibility.NEVER_RECOVER

    integrity_unhandled, _reason = get_recovery_eligibility("INTEGRITY_UNHANDLED")
    assert integrity_unhandled == RecoveryEligibility.NEVER_RECOVER


def test_eligibility_annotation_is_deterministic():
    frame = build_error_frame(
        error_code="CLI_IMPORT_MODULE_MISSING",
        error_class=ErrorClass.IMPORT,
        failed_phase=FailedPhase.CLI,
        suppressed_actions=[],
        human_summary="Missing optional module.",
        technical_details={},
        timestamp_logical=1,
    )
    eligibility, reason = get_recovery_eligibility("CLI_IMPORT_MODULE_MISSING")
    assert frame.recovery_eligibility == eligibility
    assert frame.eligibility_reason == reason


def test_registry_hash_stability():
    assert (
        recovery_eligibility_registry_hash()
        == "d75b75d3bb1951164b8b0aba5a5fa99d5cfe40337a4b91f9908737b2ac91763c"
    )
