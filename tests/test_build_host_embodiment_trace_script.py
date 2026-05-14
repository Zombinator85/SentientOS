from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from scripts import build_host_embodiment_trace as script
from sentientos.host_embodiment_trace_export import validate_trace_export_payload

pytestmark = pytest.mark.no_legacy_skip


def _run_main(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = script.main(args)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


def test_default_run_prints_valid_json_trace() -> None:
    code, stdout, stderr = _run_main([])
    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["scenario_id"] == "demo-thermal-pwm-non-mutating-ladder"
    assert payload["demo_only"] is True
    assert payload["metadata_only"] is True
    assert validate_trace_export_payload(payload).ok


def test_format_markdown_prints_summary() -> None:
    code, stdout, stderr = _run_main(["--format", "markdown"])
    assert code == 0, stderr
    assert stdout.startswith("# Host Embodiment Reviewer Demo Trace")
    assert "PWM presence is not control authority" in stdout
    assert "no host mutation" in stdout


def test_validate_only_exits_zero_without_artifact_output() -> None:
    code, stdout, stderr = _run_main(["--validate-only"])
    assert code == 0, stderr
    assert stdout == ""


def test_summary_prints_compact_reviewer_summary() -> None:
    code, stdout, stderr = _run_main(["--summary"])
    assert code == 0, stderr
    assert "Host Embodiment Reviewer Demo Trace Summary" in stdout
    assert "reviewer proof only: true" in stdout
    assert "fake/sample telemetry by default: true" in stdout


def test_output_writes_requested_file(tmp_path: Path) -> None:
    output = tmp_path / "trace.json"
    code, stdout, stderr = _run_main(["--format", "json", "--output", str(output)])
    assert code == 0, stderr
    assert stdout == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert validate_trace_export_payload(payload).ok


def test_invalid_format_exits_nonzero() -> None:
    code, stdout, stderr = _run_main(["--format", "yaml"])
    assert code != 0
    assert stdout == ""
    assert "invalid choice" in stderr


def test_invalid_output_path_exits_nonzero_without_partial_target(tmp_path: Path) -> None:
    output = tmp_path / "missing" / "trace.json"
    code, stdout, stderr = _run_main(["--output", str(output)])
    assert code != 0
    assert stdout == ""
    assert "output parent does not exist" in stderr
    assert not output.exists()


def test_script_source_does_not_call_live_collectors_or_forbidden_apis() -> None:
    source = Path("scripts/build_host_embodiment_trace.py").read_text(encoding="utf-8")
    forbidden = [
        "collect_thermal_sensor_observation",
        "collect_fan_pwm_observation",
        "socket",
        "requests",
        "urllib",
        "subprocess",
        "os.system",
        "Popen",
        "prompt_assembler",
        "admit_and_execute",
    ]
    for term in forbidden:
        assert term not in source


def test_generated_trace_includes_all_major_ladder_step_kinds_and_blocks() -> None:
    trace = script.build_trace_for_scenario("thermal_pwm_demo")
    kinds = {step.step_kind for step in trace.steps}
    for kind in [
        "collector_result",
        "host_inventory_manifest",
        "telemetry_snapshot",
        "pressure_report",
        "policy_decision",
        "proposal_receipt",
        "broker_decision",
        "broker_review_receipt",
        "fulfillment_rehearsal_receipt",
        "execution_readiness_manifest",
        "authorization_review_receipt",
        "future_authorization_schema",
        "controlled_authorization_contract",
        "controlled_authorization_grant_record",
        "controlled_authorization_revocation_record",
        "controlled_authorization_ledger",
    ]:
        assert kind in kinds
    for label in [
        "fan_pwm_write",
        "thermal_actuation",
        "service_restart",
        "power_profile_mutation",
        "file_cleanup",
        "file_delete",
        "provider_invocation",
        "network_egress",
        "prompt_assembly",
        "federation_transport",
        "remote_execution",
    ]:
        assert label in trace.blocked_action_labels
    assert validate_trace_export_payload(trace).ok
