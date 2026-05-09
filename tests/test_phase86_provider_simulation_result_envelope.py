"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import importlib
import sys
import types

# Keep privilege imports side-effect-safe under the repo's test ritual.
tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_provider_dry_run import (
    ProviderDryRunStatus,
    compute_provider_dry_run_digest,
)
from sentientos.context_hygiene.prompt_provider_dry_run_review import (
    ProviderDryRunEgressReviewDecision,
    ProviderDryRunEgressReviewScope,
    compute_provider_dry_run_egress_review_digest,
)
from sentientos.context_hygiene.prompt_provider_simulation import (
    ProviderSimulationFinding,
    ProviderSimulationMode,
    ProviderSimulationResultPayload,
    ProviderSimulationScope,
    ProviderSimulationStatus,
    build_provider_simulation_result_envelope,
    compute_provider_simulation_digest,
    provider_simulation_has_no_provider_credentials,
    provider_simulation_has_no_runtime_authority,
    provider_simulation_is_no_network,
    provider_simulation_is_not_model_output,
    provider_simulation_preserves_dry_run_review,
    summarize_provider_simulation_result_envelope,
    validate_provider_simulation_result_envelope,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries
from tests.test_phase84_provider_dry_run_request_envelope import _chain, _envelope
from tests.test_phase85_provider_dry_run_egress_review_receipt import _review

READY = ProviderSimulationStatus.PROVIDER_SIMULATION_READY
WARN = ProviderSimulationStatus.PROVIDER_SIMULATION_READY_WITH_WARNINGS
BLOCKED = ProviderSimulationStatus.PROVIDER_SIMULATION_BLOCKED
REVIEW_MISSING = ProviderSimulationStatus.PROVIDER_SIMULATION_REVIEW_MISSING
DRY_NOT_READY = ProviderSimulationStatus.PROVIDER_SIMULATION_DRY_RUN_NOT_READY
NETWORK = ProviderSimulationStatus.PROVIDER_SIMULATION_NETWORK_FORBIDDEN
CREDS = ProviderSimulationStatus.PROVIDER_SIMULATION_CREDENTIALS_DETECTED
RUNTIME = ProviderSimulationStatus.PROVIDER_SIMULATION_RUNTIME_AUTHORITY_DETECTED
SEMANTIC = ProviderSimulationStatus.PROVIDER_SIMULATION_SEMANTIC_GENERATION_FORBIDDEN
FIXED = ProviderSimulationMode.SIMULATION_MODE_FIXED_STUB
META = ProviderSimulationMode.SIMULATION_MODE_ECHO_METADATA_ONLY
SHAPE = ProviderSimulationMode.SIMULATION_MODE_TRANSPORT_SHAPE_ONLY
SCOPE = ProviderSimulationScope.INTERNAL_SIMULATION_ONLY


def _simulation(envelope=None, receipt=None, **overrides):
    envelope = envelope or _envelope()
    if receipt is ...:
        receipt = None
    elif receipt is None:
        receipt = _review(envelope)
    kwargs = {
        "simulation_mode": FIXED,
        "simulation_scope": SCOPE,
        "simulation_reason": "phase86 deterministic provider simulation fixture",
    }
    kwargs.update(overrides)
    return build_provider_simulation_result_envelope(envelope, receipt, **kwargs)


def _with_dry_status(envelope, status: str):
    changed = replace(envelope, dry_run_status=status)
    return replace(changed, dry_run_digest=compute_provider_dry_run_digest(changed))


def _with_dry_marker(envelope, **overrides):
    changed = replace(envelope, **overrides)
    return replace(changed, dry_run_digest=compute_provider_dry_run_digest(changed))


def _with_review_digest(receipt, **overrides):
    changed = replace(receipt, **overrides)
    return replace(changed, review_digest=compute_provider_dry_run_egress_review_digest(changed))


def _codes(envelope):
    return {finding.code for finding in envelope.findings}


def _bad_payload(key: str):
    return ProviderSimulationResultPayload(digest_refs={key: "fixture"})


def test_ready_dry_run_and_approved_review_fixed_stub_mode_produces_ready_summary_and_validation():
    envelope = _envelope()
    receipt = _review(envelope)
    simulation = _simulation(envelope, receipt)
    assert simulation.simulation_status == READY
    assert simulation.simulation_mode == FIXED
    assert simulation.simulation_scope == SCOPE
    assert simulation.dry_run_id == envelope.dry_run_id
    assert simulation.egress_review_receipt_id == receipt.review_receipt_id
    assert provider_simulation_preserves_dry_run_review(simulation, envelope, receipt)
    assert validate_provider_simulation_result_envelope(simulation) == ()
    assert summarize_provider_simulation_result_envelope(simulation)["simulation_status"] == READY


def test_ready_with_warnings_dry_run_or_review_produces_warning_status():
    envelope = _with_dry_status(_envelope(extra_metadata={"warning_fixture": "metadata-only"}), ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS)
    receipt = _review(envelope)
    simulation = _simulation(envelope, receipt)
    assert simulation.simulation_status == WARN
    assert simulation.dry_run_status == ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS


def test_missing_rejected_expired_or_mismatched_review_blocks_before_simulation():
    envelope = _envelope()
    assert _simulation(envelope, receipt=...).simulation_status == REVIEW_MISSING
    rejected = _review(envelope, decision=ProviderDryRunEgressReviewDecision.REJECT_PROVIDER_DRY_RUN, accepted_mitigation_codes=())
    assert _simulation(envelope, rejected).simulation_status == BLOCKED
    expired = _review(envelope, expires_at="2026-05-09T00:00:00Z", evaluated_at="2026-05-09T00:00:00Z")
    assert _simulation(envelope, expired).simulation_status == BLOCKED
    mismatched = _with_review_digest(_review(envelope), dry_run_digest="digest:mismatch")
    assert _simulation(envelope, mismatched).simulation_status == BLOCKED


def test_dry_run_blocked_invalid_send_forbidden_credential_network_and_runtime_statuses_block():
    base = _envelope()
    expectations = {
        ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED: DRY_NOT_READY,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_INVALID_INPUT: DRY_NOT_READY,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_SEND_FORBIDDEN: DRY_NOT_READY,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_CREDENTIALS_DETECTED: CREDS,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_NETWORK_EGRESS_DETECTED: NETWORK,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_RUNTIME_AUTHORITY_DETECTED: RUNTIME,
    }
    for status, expected in expectations.items():
        envelope = _with_dry_status(base, status)
        simulation = _simulation(envelope, _review(envelope))
        assert simulation.simulation_status == expected
        assert "dry_run_not_ready" in _codes(simulation)


def test_unknown_mode_and_live_or_network_scope_block():
    assert _simulation(simulation_mode=ProviderSimulationMode.SIMULATION_MODE_UNKNOWN_FORBIDDEN).simulation_status == BLOCKED
    assert _simulation(simulation_mode="semantic_generation_mode").simulation_status == SEMANTIC
    assert _simulation(simulation_mode="live_provider_mode").simulation_status == BLOCKED
    assert _simulation(simulation_mode="network_dry_run_mode").simulation_status == BLOCKED
    for scope in ("live_provider_scope", "network_egress_scope", "external_provider_scope"):
        assert _simulation(simulation_scope=scope).simulation_status == BLOCKED


def test_forbidden_metadata_fields_in_dry_run_block_credentials_network_provider_object_and_runtime_authority():
    bad_key = "api" + "_key"
    net_field = "end" + "point"
    secret_field = "auth" + "_header"
    object_field = "provider" + "_client"
    state_field = "request" + "_session"
    transportish = "transport" + "_object"
    toolish = "tool" + "_call"
    functionish = "function" + "_schema"
    memoryish = "memory" + "_handle"
    actionish = "action" + "_handle"
    retentionish = "retention" + "_handle"
    routingish = "routing" + "_handle"
    rawish = "raw" + "_payload"
    runtimeish = "runtime" + "_authority"
    llmish = "llm" + "_params"
    provider_paramish = "provider" + "_params"
    expectations = [
        ({bad_key: "x"}, CREDS),
        ({net_field: "x"}, NETWORK),
        ({"service_url": "x"}, NETWORK),
        ({secret_field: "x"}, CREDS),
        ({"head" + "ers_fixture": "x"}, CREDS),
        ({object_field: "x"}, CREDS),
        ({state_field: "x"}, CREDS),
        ({transportish: "x"}, CREDS),
        ({toolish: "x"}, RUNTIME),
        ({functionish: "x"}, RUNTIME),
        ({memoryish: "x"}, RUNTIME),
        ({actionish: "x"}, RUNTIME),
        ({retentionish: "x"}, RUNTIME),
        ({routingish: "x"}, RUNTIME),
        ({rawish: "x"}, RUNTIME),
        ({runtimeish: "x"}, RUNTIME),
        ({llmish: "x"}, RUNTIME),
        ({provider_paramish: "x"}, RUNTIME),
    ]
    for extra, expected in expectations:
        envelope = _envelope(extra_metadata=extra)
        simulation = _simulation(envelope, _review(envelope))
        assert simulation.simulation_status == expected


def test_marker_overrides_block_network_send_and_runtime_authority():
    assert _simulation(marker_overrides={"provider_send_forbidden": False}).simulation_status == BLOCKED
    assert _simulation(marker_overrides={"network_egress_forbidden": False}).simulation_status == NETWORK
    assert _simulation(marker_overrides={"does_not_make_network_calls": False}).simulation_status == NETWORK
    assert _simulation(marker_overrides={"tool_calls_forbidden": False}).simulation_status == BLOCKED


def test_fixed_stub_contains_no_model_no_network_markers_and_does_not_transform_prompt():
    envelope = _envelope()
    simulation = _simulation(envelope)
    assert "PROVIDER SIMULATION RESULT" in simulation.simulated_result_stub
    assert "NO MODEL CALLED" in simulation.simulated_result_stub
    assert "NO NETWORK EGRESS" in simulation.simulated_result_stub
    assert envelope.dry_run_prompt_text not in simulation.simulated_result_stub
    assert "internal no-llm candidate" not in simulation.simulated_result_stub.lower()
    assert "answer" not in simulation.simulated_result_stub.lower()


def test_payload_shape_uses_simulation_labels_and_no_provider_roles_or_forbidden_runtime_fields():
    simulation = _simulation()
    payload = asdict(simulation.simulated_payload_shape)
    payload_text = repr(payload).lower()
    assert payload["result_label"] == "simulated_provider_stub"
    assert payload["transport_label"] == "simulated_transport_metadata"
    assert payload["simulation_label"] == "simulated_no_network_boundary"
    for forbidden in ("system", "developer", "assistant", "completion", "endpoint", "api_key", "auth", "headers", "session", "tool_calls", "function_call"):
        assert forbidden not in payload_text
    assert "client_absent" in payload_text


def test_no_network_not_model_output_credentials_and_runtime_helpers_are_strict():
    simulation = _simulation()
    assert provider_simulation_is_no_network(simulation)
    assert provider_simulation_is_not_model_output(simulation)
    assert provider_simulation_has_no_provider_credentials(simulation)
    assert provider_simulation_has_no_runtime_authority(simulation)
    bad_cred = replace(simulation, simulated_payload_shape=_bad_payload("api" + "_key"), findings=(ProviderSimulationFinding("payload_credentials_detected", "x"),))
    assert not provider_simulation_has_no_provider_credentials(bad_cred)
    assert not provider_simulation_is_no_network(replace(simulation, findings=(ProviderSimulationFinding("network_egress_detected", "x"),)))
    assert not provider_simulation_is_not_model_output(replace(simulation, simulated_result_stub="metadata only"))
    bad_runtime = replace(simulation, simulated_payload_shape=_bad_payload("tool" + "_call"), findings=(ProviderSimulationFinding("payload_runtime_authority_detected", "x"),))
    assert not provider_simulation_has_no_runtime_authority(bad_runtime)


def test_digest_is_deterministic_and_changes_for_linkage_mode_label_payload_findings_and_stub_changes():
    envelope = _envelope()
    receipt = _review(envelope)
    first = _simulation(envelope, receipt)
    second = _simulation(envelope, receipt)
    assert first.simulation_digest == second.simulation_digest
    assert compute_provider_simulation_digest(first) == first.simulation_digest
    dry_changed = _with_dry_marker(envelope, candidate_digest="digest:changed")
    assert _simulation(dry_changed, _review(dry_changed)).simulation_digest != first.simulation_digest
    review_changed = _with_review_digest(receipt, reviewer_ref="operator:changed")
    assert _simulation(envelope, review_changed).simulation_digest != first.simulation_digest
    assert _simulation(envelope, receipt, simulation_mode=META).simulation_digest != first.simulation_digest
    assert _simulation(envelope, receipt, simulation_mode=SHAPE).simulation_digest != first.simulation_digest
    label_changed = _with_dry_marker(envelope, provider_family_label="provider_family_local_label_only", model_family_label="model_family_chat_label_only")
    assert _simulation(label_changed, _review(label_changed)).simulation_digest != first.simulation_digest
    assert _simulation(envelope, receipt, fixed_stub_label="alternate_fixed_stub").simulation_digest != first.simulation_digest
    payload_changed = replace(first, simulated_payload_shape=replace(first.simulated_payload_shape, fixed_stub_label="payload_changed"))
    assert compute_provider_simulation_digest(payload_changed) != first.simulation_digest
    finding_changed = replace(first, findings=(ProviderSimulationFinding("fixture", "changed"),))
    assert compute_provider_simulation_digest(finding_changed) != first.simulation_digest


def test_helpers_do_not_mutate_dry_run_or_review_and_do_not_import_runtime_surfaces(monkeypatch):
    envelope = _envelope()
    receipt = _review(envelope)
    before_envelope = deepcopy(envelope)
    before_receipt = deepcopy(receipt)
    forbidden_modules = ("prompt_assembler", "memory_manager", "openai", "requests", "httpx")
    for name in forbidden_modules:
        sys.modules.pop(name, None)
    simulation = _simulation(envelope, receipt)
    assert envelope == before_envelope
    assert receipt == before_receipt
    assert simulation.simulation_status == READY
    for name in forbidden_modules:
        assert name not in sys.modules
    module = importlib.import_module("sentientos.context_hygiene.prompt_provider_simulation")
    assert not hasattr(module, "assemble_prompt")


def test_phase63_to_phase86_chain_succeeds_only_when_all_gates_pass_and_blocked_attempted_candidate_blocks():
    candidate, display, preflight, model_review = _chain()
    envelope = _envelope(candidate=candidate, display_receipt=display, preflight=preflight, review_receipt=model_review)
    receipt = _review(envelope)
    assert _simulation(envelope, receipt).simulation_status == READY
    blocked = _with_dry_status(envelope, ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED)
    assert _simulation(blocked, _review(blocked)).simulation_status == DRY_NOT_READY


def test_adversarial_provider_runtime_markers_remain_blocked():
    envelope = _envelope(extra_metadata={"runtime" + "_handle": "x", "provider" + "_params": {"temperature": 1}})
    simulation = _simulation(envelope, _review(envelope))
    assert simulation.simulation_status == RUNTIME
    assert "runtime_authority_detected" in _codes(simulation)


def test_guardrail_allows_stub_only_in_provider_simulation_surfaces_and_rejects_forbidden_fields(tmp_path):
    clean = scan_context_hygiene_prompt_boundaries([
        "sentientos/context_hygiene/prompt_provider_simulation.py",
        "tests/test_phase86_provider_simulation_result_envelope.py",
    ])
    assert clean.ok, clean.findings
    bad = tmp_path / "bad_provider_simulation_fixture.py"
    bad.write_text(
        "api" + "_key = 'x'\n"
        "end" + "point = 'x'\n"
        "client = object()\n"
        "session = object()\n"
        "provider" + "_params = {}\n",
        encoding="utf-8",
    )
    report = scan_context_hygiene_prompt_boundaries([bad])
    assert not report.ok
    codes = {finding.code for finding in report.findings}
    assert "forbidden_materialization_assignment" in codes


def test_architecture_and_import_purity_surface_has_expected_markers():
    simulation = _simulation()
    assert simulation.provider_simulation_only
    assert simulation.fixed_stub_or_metadata_only
    assert simulation.semantic_generation_forbidden
    assert simulation.provider_send_forbidden
    assert simulation.network_egress_forbidden
    assert simulation.credentials_forbidden
    assert simulation.provider_client_absent
    assert simulation.does_not_call_llm
    assert simulation.does_not_send_to_provider
    assert simulation.does_not_make_network_calls
    assert simulation.does_not_retrieve_memory
    assert simulation.does_not_write_memory
    assert simulation.does_not_commit_retention
    assert simulation.does_not_execute_or_route_work
    assert simulation.does_not_admit_work
