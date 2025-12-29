import json

from sentientos.diagnostics import (
    ErrorClass,
    FailedPhase,
    LogicalClock,
    build_error_frame,
    frame_exception,
)


def test_diagnostic_frame_hash_deterministic():
    clock = LogicalClock()
    frame_one = build_error_frame(
        error_code="CLI_IMPORT_MODULE_MISSING",
        error_class=ErrorClass.IMPORT,
        failed_phase=FailedPhase.CLI,
        suppressed_actions=["auto_recovery"],
        human_summary="Missing optional module.",
        technical_details={"module": "agents.forms.review_bundle"},
        timestamp_logical=clock.tick(),
    )
    frame_two = build_error_frame(
        error_code="CLI_IMPORT_MODULE_MISSING",
        error_class=ErrorClass.IMPORT,
        failed_phase=FailedPhase.CLI,
        suppressed_actions=["auto_recovery"],
        human_summary="Missing optional module.",
        technical_details={"module": "agents.forms.review_bundle"},
        timestamp_logical=frame_one.timestamp_logical,
    )
    assert frame_one.content_hash() == frame_two.content_hash()


def test_diagnostic_frame_redaction():
    frame = build_error_frame(
        error_code="INVARIANT_VIOLATION",
        error_class=ErrorClass.INTEGRITY,
        failed_phase=FailedPhase.CLI,
        suppressed_actions=[],
        human_summary="Redaction check.",
        technical_details={"password": "secret", "nested": {"token": "abc"}},
        timestamp_logical=1,
    )
    payload = json.loads(frame.to_json())
    assert payload["technical_details"]["password"] == "***"
    assert payload["technical_details"]["nested"]["token"] == "***"


def test_diagnostic_frame_suppressed_actions_reporting():
    frame = build_error_frame(
        error_code="EXECUTION_UNHANDLED",
        error_class=ErrorClass.EXECUTION,
        failed_phase=FailedPhase.CLI,
        suppressed_actions=["auto_recovery", "retry"],
        human_summary="Suppressed actions recorded.",
        technical_details={},
        timestamp_logical=3,
    )
    payload = json.loads(frame.to_json())
    assert payload["suppressed_actions"] == ["auto_recovery", "retry"]


def test_import_time_error_framing():
    error = ModuleNotFoundError("missing module")
    frame = frame_exception(error, failed_phase=FailedPhase.IMPORT, suppressed_actions=[])
    assert frame.error_class == ErrorClass.IMPORT
    assert frame.error_code == "IMPORT_MODULE_MISSING"
