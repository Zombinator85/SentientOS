"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import importlib
import sys
import types
from pathlib import Path

# Keep privilege imports side-effect-safe under the repo's test ritual.
tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_provider_dry_run import ProviderDryRunStatus, compute_provider_dry_run_digest
from sentientos.context_hygiene.prompt_provider_dry_run_review import (
    ProviderDryRunEgressReviewDecision,
    ProviderDryRunEgressReviewScope,
    compute_provider_dry_run_egress_review_digest,
)
from sentientos.context_hygiene.prompt_provider_simulation import (
    ProviderSimulationStatus,
    compute_provider_simulation_digest,
)
from sentientos.context_hygiene.prompt_network_egress_preflight import (
    ProviderNetworkEgressPreflightRing,
    ProviderNetworkEgressPreflightStatus,
    build_provider_network_egress_preflight,
    compute_provider_network_egress_preflight_digest,
    explain_provider_network_egress_preflight_findings,
    provider_network_egress_preflight_allows_future_review_gate,
    provider_network_egress_preflight_digest_chain_complete,
    provider_network_egress_preflight_forbids_network,
    provider_network_egress_preflight_forbids_provider_send,
    provider_network_egress_preflight_has_no_credentials,
    provider_network_egress_preflight_has_no_runtime_authority,
    summarize_provider_network_egress_preflight,
    validate_provider_network_egress_preflight,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries
from tests.test_phase84_provider_dry_run_request_envelope import _chain, _envelope
from tests.test_phase85_provider_dry_run_egress_review_receipt import _review
from tests.test_phase86_provider_simulation_result_envelope import _simulation

REPO_ROOT = Path(__file__).resolve().parents[1]
READY = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW
WARN = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS
REVIEW = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED
DENIED = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DENIED
INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_INVALID_INPUT
DRY_INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DRY_RUN_INVALID
REVIEW_INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_INVALID
SIM_INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_SIMULATION_INVALID
CREDS = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED
NETWORK = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN
RUNTIME = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
PREFLIGHT_ONLY = ProviderNetworkEgressPreflightRing.NETWORK_EGRESS_REVIEW_PREFLIGHT_ONLY
FUTURE_EGRESS = ProviderNetworkEgressPreflightRing.FUTURE_NETWORK_EGRESS_REVIEW_GATE
FUTURE_DRY = ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE
LIVE_FORBIDDEN = ProviderNetworkEgressPreflightRing.LIVE_PROVIDER_SEND_FORBIDDEN
FLAGS = {"network_egress_preflight": True}


def _preflight(envelope=None, receipt=None, simulation=None, **overrides):
    envelope = envelope if envelope is not None else _envelope()
    receipt = receipt if receipt is not None else _review(envelope)
    simulation = simulation if simulation is not None else _simulation(envelope, receipt)
    kwargs = {"requested_ring": PREFLIGHT_ONLY, "feature_flag_state": FLAGS}
    kwargs.update(overrides)
    return build_provider_network_egress_preflight(envelope, receipt, simulation, **kwargs)


def _codes(preflight):
    return {finding.code for finding in preflight.findings}


def _with_dry_digest(envelope, **overrides):
    changed = replace(envelope, **overrides)
    return replace(changed, dry_run_digest=compute_provider_dry_run_digest(changed))


def _with_review_digest(receipt, **overrides):
    changed = replace(receipt, **overrides)
    return replace(changed, review_digest=compute_provider_dry_run_egress_review_digest(changed))


def _with_sim_digest(simulation, **overrides):
    changed = replace(simulation, **overrides)
    return replace(changed, simulation_digest=compute_provider_simulation_digest(changed))


def test_valid_dry_run_review_simulation_preflight_only_yields_ready_for_review():
    preflight = _preflight()
    assert preflight.preflight_status == READY
    assert preflight.requested_ring == PREFLIGHT_ONLY
    assert preflight.effective_ring == PREFLIGHT_ONLY
    assert validate_provider_network_egress_preflight(preflight) == ()
    assert summarize_provider_network_egress_preflight(preflight)["preflight_status"] == READY
    assert provider_network_egress_preflight_digest_chain_complete(preflight)


def test_future_review_and_future_provider_dry_run_rings_remain_review_or_warning_only():
    e = _envelope(); r = _review(e); s = _simulation(e, r)
    future_review = _preflight(e, r, s, requested_ring=FUTURE_EGRESS)
    future_dry = _preflight(e, r, s, requested_ring=FUTURE_DRY)
    assert future_review.preflight_status == REVIEW
    assert future_dry.preflight_status == WARN
    assert future_dry.warnings
    assert provider_network_egress_preflight_allows_future_review_gate(future_review)
    assert provider_network_egress_preflight_allows_future_review_gate(future_dry)


def test_live_provider_send_forbidden_and_unknown_ring_deny():
    assert _preflight(requested_ring=LIVE_FORBIDDEN).preflight_status == DENIED
    unknown = _preflight(requested_ring="unknown_ring")
    assert unknown.preflight_status == DENIED
    assert "requested_ring_unknown" in _codes(unknown)


def test_missing_artifacts_and_not_ready_upstream_statuses_are_invalid_or_denied():
    e = _envelope(); r = _review(e); s = _simulation(e, r)
    assert build_provider_network_egress_preflight(None, r, s, requested_ring=PREFLIGHT_ONLY, feature_flag_state=FLAGS).preflight_status == INVALID
    assert build_provider_network_egress_preflight(e, None, s, requested_ring=PREFLIGHT_ONLY, feature_flag_state=FLAGS).preflight_status == REVIEW_INVALID
    assert build_provider_network_egress_preflight(e, r, None, requested_ring=PREFLIGHT_ONLY, feature_flag_state=FLAGS).preflight_status == INVALID
    dry_blocked = _with_dry_digest(e, dry_run_status=ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED)
    assert _preflight(dry_blocked, _review(dry_blocked), _simulation(dry_blocked, _review(dry_blocked))).preflight_status in {DRY_INVALID, NETWORK, RUNTIME}
    sim_blocked = _with_sim_digest(s, simulation_status=ProviderSimulationStatus.PROVIDER_SIMULATION_BLOCKED)
    assert _preflight(e, r, sim_blocked).preflight_status in {SIM_INVALID, NETWORK, RUNTIME}


def test_dry_run_non_sendable_review_satisfaction_and_simulation_preservation_are_required():
    e = _envelope(); r = _review(e); s = _simulation(e, r)
    not_sendable = replace(e, non_sendable=False)
    assert _preflight(not_sendable, r, s).preflight_status == DRY_INVALID
    expired = _review(e, expires_at="2026-05-09T00:00:00Z", evaluated_at="2026-05-09T00:00:00Z")
    assert _preflight(e, expired, _simulation(e, expired)).preflight_status == REVIEW_INVALID
    mismatched = _with_review_digest(r, dry_run_digest="digest:mismatch")
    assert _preflight(e, mismatched, s).preflight_status == REVIEW_INVALID
    rejected = _review(e, decision=ProviderDryRunEgressReviewDecision.REJECT_PROVIDER_DRY_RUN, accepted_mitigation_codes=())
    assert _preflight(e, rejected, _simulation(e, rejected)).preflight_status == REVIEW_INVALID
    bad_sim = _with_sim_digest(s, egress_review_digest="digest:mismatch")
    assert _preflight(e, r, bad_sim).preflight_status == SIM_INVALID


def test_simulation_no_network_and_not_model_output_helpers_are_hard_gates():
    e = _envelope(); r = _review(e); s = _simulation(e, r)
    no_network = replace(s, does_not_make_network_calls=False)
    assert _preflight(e, r, no_network).preflight_status == NETWORK
    semantic = replace(s, simulated_result_stub="metadata only", semantic_generation_forbidden=False)
    assert _preflight(e, r, semantic).preflight_status == SIM_INVALID


def test_digest_chain_incomplete_and_mismatch_record_deterministic_findings():
    e = _envelope(); r = _review(e); s = _simulation(e, r)
    missing = replace(s, simulation_digest="")
    preflight = _preflight(e, r, missing)
    assert preflight.preflight_status == DENIED
    assert "digest_chain_incomplete" in _codes(preflight)
    mismatch = replace(s, dry_run_digest="digest:mismatch")
    preflight = _preflight(e, r, mismatch)
    assert preflight.preflight_status in {DENIED, SIM_INVALID}
    assert "digest_chain_incomplete" in _codes(preflight)


def test_missing_or_disabled_feature_flag_denies():
    assert _preflight(feature_flag_state={}).preflight_status == DENIED
    assert _preflight(feature_flag_state={"network_egress_preflight": False}).preflight_status == DENIED


def test_forbidden_marker_evidence_denies_credentials_network_provider_objects_runtime_raw_and_params():
    cases = [
        ({"api" + "_key": "present"}, CREDS),
        ({"credential_marker": "present"}, CREDS),
        ({"auth" + "_header": "present"}, CREDS),
        ({"end" + "point": "present"}, NETWORK),
        ({"service_url": "present"}, NETWORK),
        ({"provider" + "_client": "present"}, NETWORK),
        ({"request" + "_session": "present"}, NETWORK),
        ({"transport" + "_object": "present"}, NETWORK),
        ({"tool" + "_call": "present"}, RUNTIME),
        ({"memory" + "_handle": "present"}, RUNTIME),
        ({"retention" + "_handle": "present"}, RUNTIME),
        ({"action" + "_handle": "present"}, RUNTIME),
        ({"routing" + "_handle": "present"}, RUNTIME),
        ({"raw" + "_payload": "present"}, RUNTIME),
        ({"runtime" + "_handle": "present"}, RUNTIME),
        ({"model" + "_params": "present"}, RUNTIME),
        ({"provider" + "_params": "present"}, RUNTIME),
    ]
    for evidence, expected in cases:
        assert _preflight(marker_evidence=evidence).preflight_status == expected


def test_forbidden_allowances_and_required_no_runtime_flags_deny():
    allowances = [
        "network_egress_allowed", "provider_send_allowed", "credentials_allowed", "provider_client_allowed",
        "llm_call_allowed", "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed",
        "memory_write_allowed", "retention_allowed", "action_execution_allowed", "routing_allowed",
    ]
    for allowance in allowances:
        assert _preflight(allowance_overrides={allowance: True}).preflight_status == RUNTIME
    flags = ["internal_only", "no_network", "no_provider_send", "no_credentials", "no_provider_client", "no_semantic_generation", "no_tools", "no_memory", "no_retention", "no_actions", "no_routing"]
    for flag in flags:
        assert _preflight(**{flag: False}).preflight_status == RUNTIME


def test_output_allowances_are_false_and_forbidden_markers_are_preserved():
    preflight = _preflight()
    for field in (
        "network_egress_allowed", "provider_send_allowed", "credentials_allowed", "provider_client_allowed", "llm_call_allowed",
        "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed", "retention_allowed",
        "action_execution_allowed", "routing_allowed",
    ):
        assert getattr(preflight, field) is False
    assert provider_network_egress_preflight_forbids_network(preflight)
    assert provider_network_egress_preflight_forbids_provider_send(preflight)
    assert provider_network_egress_preflight_has_no_credentials(preflight)
    assert provider_network_egress_preflight_has_no_runtime_authority(preflight)
    assert preflight.network_egress_preflight_only is True
    assert preflight.provider_send_forbidden is True
    assert preflight.credentials_forbidden is True
    assert preflight.provider_client_forbidden is True
    assert preflight.llm_call_forbidden is True
    assert preflight.semantic_generation_forbidden is True


def test_allows_future_review_gate_false_for_denials_and_true_for_ready_warning_review_required():
    assert provider_network_egress_preflight_allows_future_review_gate(_preflight())
    assert provider_network_egress_preflight_allows_future_review_gate(_preflight(requested_ring=FUTURE_EGRESS))
    assert provider_network_egress_preflight_allows_future_review_gate(_preflight(requested_ring=FUTURE_DRY))
    assert not provider_network_egress_preflight_allows_future_review_gate(_preflight(feature_flag_state={}))


def test_digest_is_deterministic_and_changes_for_required_stable_fields():
    e = _envelope(); r = _review(e); s = _simulation(e, r)
    first = _preflight(e, r, s)
    second = _preflight(e, r, s)
    assert first.preflight_digest == second.preflight_digest
    assert compute_provider_network_egress_preflight_digest(first) == first.preflight_digest
    dry_changed = _with_dry_digest(e, candidate_digest="digest:changed")
    review_changed = _review(dry_changed)
    sim_changed_dry = _simulation(dry_changed, review_changed)
    assert _preflight(dry_changed, review_changed, sim_changed_dry).preflight_digest != first.preflight_digest
    sim_changed = _with_sim_digest(s, simulation_reason="changed")
    assert _preflight(e, r, sim_changed).preflight_digest != first.preflight_digest
    review_changed2 = _with_review_digest(r, reviewer_ref="operator:changed")
    sim_changed_review = _simulation(e, review_changed2)
    assert _preflight(e, review_changed2, sim_changed_review).preflight_digest != first.preflight_digest
    assert _preflight(e, r, s, requested_ring=FUTURE_EGRESS).preflight_digest != first.preflight_digest
    assert _preflight(e, r, s, feature_flag_state={}).preflight_digest != first.preflight_digest


def test_helper_does_not_mutate_inputs():
    e = _envelope(); r = _review(e); s = _simulation(e, r)
    before = (deepcopy(asdict(e)), deepcopy(asdict(r)), deepcopy(asdict(s)))
    _preflight(e, r, s)
    assert before == (asdict(e), asdict(r), asdict(s))


def test_helper_does_not_import_or_call_runtime_surfaces_and_guardrail_scans_new_module():
    for module in ("prompt_assembler", "memory_manager", "openai", "requests", "httpx"):
        sys.modules.pop(module, None)
    mod = importlib.import_module("sentientos.context_hygiene.prompt_network_egress_preflight")
    _preflight()
    assert hasattr(mod, "build_provider_network_egress_preflight")
    for module in ("prompt_assembler", "memory_manager", "openai", "requests", "httpx"):
        assert module not in sys.modules
    report = scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    assert "sentientos/context_hygiene/prompt_network_egress_preflight.py" in report.scanned_paths
    assert report.ok


def test_phase63_to_phase87_chain_and_blocked_attempted_candidate_denial():
    candidate, display, preflight, review = _chain()
    e = _envelope(chain=(candidate, display, preflight, review))
    r = _review(e)
    s = _simulation(e, r)
    assert _preflight(e, r, s).preflight_status == READY
    blocked_e = _with_dry_digest(e, dry_run_status=ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED)
    blocked_r = _review(blocked_e)
    blocked_s = _simulation(blocked_e, blocked_r)
    denied = _preflight(blocked_e, blocked_r, blocked_s)
    assert denied.preflight_status in {DRY_INVALID, NETWORK, RUNTIME}
    assert not provider_network_egress_preflight_allows_future_review_gate(denied)


def test_adversarial_provider_runtime_markers_remain_denied_and_findings_are_explainable():
    preflight = _preflight(marker_evidence={"provider" + "_client": "present", "runtime" + "_handle": "present"})
    assert preflight.preflight_status in {NETWORK, RUNTIME}
    assert explain_provider_network_egress_preflight_findings(preflight)


def test_architecture_import_purity_surfaces_remain_acceptable_for_phase87_module():
    report = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_network_egress_preflight.py"], repo_root=REPO_ROOT)
    assert report.ok
