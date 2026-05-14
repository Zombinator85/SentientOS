from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.host_embodiment_trace import build_host_embodiment_demo_trace
from sentientos.host_embodiment_trace_export import (
    serialize_host_embodiment_trace_json,
    serialize_host_embodiment_trace_markdown,
    validate_trace_export_payload,
    write_trace_export_artifact,
)

pytestmark = pytest.mark.no_legacy_skip


def test_json_serialization_is_deterministic_and_matches_golden_fixture() -> None:
    trace = build_host_embodiment_demo_trace(scenario_id="demo-thermal-pwm-non-mutating-ladder")
    first = serialize_host_embodiment_trace_json(trace)
    second = serialize_host_embodiment_trace_json(trace)
    fixture = Path("tests/fixtures/host_embodiment_trace_thermal_pwm_demo.json").read_text(encoding="utf-8")
    assert first == second
    assert first == fixture
    assert '"scenario_id": "demo-thermal-pwm-non-mutating-ladder"' in first
    assert first.index('"blocked_action_labels"') < first.index('"created_at"')


def test_markdown_serialization_contains_reviewer_proof_language() -> None:
    trace = build_host_embodiment_demo_trace()
    markdown = serialize_host_embodiment_trace_markdown(trace)
    for expected in [
        "Thermal + PWM presence proves telemetry is not control authority",
        "Trace status",
        "Step count",
        "collector results",
        "metadata-only ledger",
        "PWM presence is not control authority",
        "controlled authorization contract is not a live grant",
        "Grant/revocation records are schema-only/future-use-only",
        "Real actuation remains deferred",
        "no live authorization",
        "no host mutation",
        "no effect",
        "no network",
        "no provider",
        "no prompt assembly",
        "fake/sample thermal+PWM telemetry",
    ]:
        assert expected in markdown


def test_validation_rejects_payload_claiming_forbidden_activity() -> None:
    trace = build_host_embodiment_demo_trace().to_dict()
    for flag in [
        "live_authorization_granted",
        "effect_performed",
        "host_mutation_performed",
        "network_performed",
        "provider_invocation_performed",
        "prompt_assembly_performed",
    ]:
        bad = dict(trace)
        bad[flag] = True
        result = validate_trace_export_payload(bad)
        assert not result.ok
        assert f"export_forbidden_flag:{flag}" in result.findings


def test_validation_rejects_step_claiming_host_mutation_or_effect() -> None:
    payload = build_host_embodiment_demo_trace().to_dict()
    steps = list(payload["steps"])
    steps[0] = dict(steps[0], effect_performed=True, host_mutation_performed=True)
    payload["steps"] = steps
    result = validate_trace_export_payload(payload)
    assert not result.ok
    assert any("export_step_claims_effect" in finding for finding in result.findings)
    assert any("export_step_claims_host_mutation" in finding for finding in result.findings)


def test_validation_rejects_missing_blocked_and_deferred_labels() -> None:
    payload = build_host_embodiment_demo_trace().to_dict()
    payload["blocked_action_labels"] = []
    payload["deferred_capability_labels"] = []
    result = validate_trace_export_payload(payload)
    assert not result.ok
    assert any("export_missing_blocked_actions" in finding for finding in result.findings)
    assert any("export_missing_deferred_capabilities" in finding for finding in result.findings)


def test_validation_rejects_trace_object_claiming_live_authorization() -> None:
    trace = replace(build_host_embodiment_demo_trace(), live_authorization_granted=True)
    result = validate_trace_export_payload(trace)
    assert not result.ok
    assert "trace_forbidden_flag:live_authorization_granted" in result.findings


def test_output_artifact_writes_only_explicit_path_and_is_deterministic(tmp_path: Path) -> None:
    trace = build_host_embodiment_demo_trace()
    content = serialize_host_embodiment_trace_json(trace)
    output = tmp_path / "explicit" / "trace.json"
    with pytest.raises(ValueError):
        write_trace_export_artifact(output, content)
    written = write_trace_export_artifact(output, content, create_parent=True)
    assert written == output
    assert output.read_text(encoding="utf-8") == content
    write_trace_export_artifact(output, content, create_parent=True)
    assert output.read_text(encoding="utf-8") == content
    assert not (tmp_path / "trace.json").exists()


def test_golden_fixture_contains_no_secrets_real_host_identifiers_or_provider_endpoints() -> None:
    fixture = Path("tests/fixtures/host_embodiment_trace_thermal_pwm_demo.json").read_text(encoding="utf-8").lower()
    for forbidden in [
        "api_key",
        "secret",
        "token",
        "bearer",
        "password",
        "/home/",
        "c:\\users",
        "prompt text",
        "openai",
        "anthropic",
        "http://",
        "https://",
    ]:
        assert forbidden not in fixture
