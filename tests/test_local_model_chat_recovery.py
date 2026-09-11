from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from sentientos import local_model_production_serving as serving
from sentientos.control_plane_kernel import (AdmissionOutcome, AuthorityClass,
                                              ControlActionRequest, ControlPlaneKernel,
                                              LifecyclePhase)
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.runtime.local_model_chat_recovery import (
    LocalModelChatRecoveryError,
    build_recovery_intent,
    build_startup_snapshot,
    require_fresh_operation,
    verified_serving_receipts,
)
from sentientos.runtime.local_model_chat_service import LocalModelChatServiceAdapter, LocalModelChatStartup

pytestmark = pytest.mark.no_legacy_skip


def activation() -> dict:
    state = {"state_semantic_digest": "a" * 64, "generation": 7, "model_id": "model-1",
             "artifact_id": "artifact-1", "runtime_id": "runtime-1", "authority_map_digest": "map-1"}
    return {"active_state": state, "activation_receipt": {
        "receipt_id": "activation-1", "receipt_semantic_digest": "activation-digest"}}


def receipt(operation: str = "serve-1") -> dict:
    provenance = {"activation_state_semantic_digest": "a" * 64, "activation_generation": 7,
        "activation_receipt_id": "activation-1", "activation_receipt_semantic_digest": "activation-digest",
        "model_id": "model-1", "artifact_id": "artifact-1", "runtime_id": "runtime-1",
        "authority_map_digest": "map-1"}
    value = {"schema_version": "sentientos.local_model_serving_session_receipt:v1",
        "receipt_id": "receipt-" + operation, "session_id": "session-" + operation,
        "binding": {"installation_identity": "install-1", "serving_operation_id": operation, **provenance},
        "control_plane_authority_class": "model_serving", "admission_outcome": "allow",
        "model_loaded": True, "serving_session_bound": True, "inference_performed": False}
    value["receipt_semantic_digest"] = semantic_digest(value)
    return value


def snapshot() -> dict:
    return build_startup_snapshot(LocalModelChatStartup(True, "install-1", "serve-1"), "generation-1")


def test_approved_unchanged_activation_recovery_intent_is_deterministic_and_zero_inference() -> None:
    arguments = dict(snapshot=snapshot(), prior_receipt=receipt(), activation=activation(),
                     replacement_serving_operation_id="serve-2", recovery_correlation_id="recover-1")
    first = build_recovery_intent(**arguments)
    assert first == build_recovery_intent(**arguments)
    assert first["runtime_supervisor_generation"] == "generation-1"
    assert first["startup_configuration_digest"] == snapshot()["startup_configuration_digest"]
    assert first["prior_serving_receipt_semantic_digest"] == receipt()["receipt_semantic_digest"]
    assert first["activation_state_semantic_digest"] == "a" * 64
    assert first["recovery_inference"] is False


@pytest.mark.parametrize("replacement", ["", "*", "latest", "serve-1"])
def test_replacement_operation_must_be_nonplaceholder_and_different(replacement: str) -> None:
    with pytest.raises((LocalModelChatRecoveryError, RuntimeError)):
        build_recovery_intent(snapshot=snapshot(), prior_receipt=receipt(), activation=activation(),
            replacement_serving_operation_id=replacement, recovery_correlation_id="recover-1")


def test_globally_fresh_replacement_operation_rejects_any_older_lifetime(tmp_path: Path) -> None:
    handle = InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("install-1"), create=True)
    directory = handle.fixed_object("local-model/serving/receipts"); handle.ensure_directory(directory)
    import json
    old = receipt("serve-old")
    handle.durable_create(directory.child("old.json"), (json.dumps(old, sort_keys=True, separators=(",", ":")) + "\n").encode())
    assert len(verified_serving_receipts(handle)) == 1
    with pytest.raises(LocalModelChatRecoveryError, match="reused"):
        require_fresh_operation(handle, "serve-old", "serve-1")


def test_malformed_prior_serving_receipt_fails_closed(tmp_path: Path) -> None:
    handle = InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("install-1"), create=True)
    directory = handle.fixed_object("local-model/serving/receipts"); handle.ensure_directory(directory)
    handle.durable_create(directory.child("bad.json"), b"{}\n")
    with pytest.raises(LocalModelChatRecoveryError, match="malformed"):
        verified_serving_receipts(handle)


def test_activation_race_guard_fails_before_model_serving_admission(monkeypatch, tmp_path: Path) -> None:
    handle = InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("install-1"), create=True)
    observed = activation(); observed["active_state"]["installation_identity"] = "install-1"
    observed["activation_receipt"]["resulting_state_digest"] = "a" * 64
    observed["catalog_proof"] = {}
    monkeypatch.setattr(serving, "verify_current_activation", lambda *_a, **_k: observed)
    class Kernel:
        def admit(self, _request): pytest.fail("MODEL_SERVING admission must not occur")
    controller = serving.ProductionServingController(handle, Kernel(), model_factory=lambda *_a: pytest.fail("load"))
    with pytest.raises(serving.ProductionServingError, match="expected_activation_state_mismatch"):
        controller.establish(operation_id="serve-2", expected_activation_state_digest="b" * 64)


def test_exact_restart_preserves_fixed_custody_and_passes_activation_guard(monkeypatch) -> None:
    adapter = LocalModelChatServiceAdapter(LocalModelChatStartup(True, "install-1", "serve-1", port=5500))
    monkeypatch.setattr(adapter, "stop", lambda: None)
    monkeypatch.setattr("sentientos.runtime.services.ChildProcessServiceAdapter.start", lambda _self: None)
    adapter._restart_with_fresh_serving_operation(replacement_serving_operation_id="serve-2",
                                                   expected_activation_state_digest="a" * 64)
    assert adapter.startup_configuration == LocalModelChatStartup(True, "install-1", "serve-2", port=5500)
    assert adapter._argv[-2:] == ("--expected-activation-state-digest", "a" * 64)
    assert Path(adapter._argv[1]).name == "local_model_chat.py"


def test_recovery_surface_has_no_generic_process_or_model_escape() -> None:
    parameters = set(inspect.signature(LocalModelChatServiceAdapter._restart_with_fresh_serving_operation).parameters)
    assert parameters == {"self", "replacement_serving_operation_id", "expected_activation_state_digest"}
    forbidden = {"argv", "executable", "script", "model", "backend", "runtime_path", "activation_path"}
    assert not parameters & forbidden


def test_daemon_restart_independent_admission_uses_real_control_plane_kernel(tmp_path: Path) -> None:
    correlation = "local-model-chat-recovery:integration-1"
    decision = ControlPlaneKernel(decisions_path=tmp_path / "decisions.jsonl").admit(ControlActionRequest(
        action_kind="restart_daemon", authority_class=AuthorityClass.DAEMON_RESTART,
        actor="deterministic_local_model_chat_recovery_controller",
        target_subsystem="local_model_chat", requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": correlation, "subject": "local_model_chat", "recovery_scope": "local"}))
    assert decision.outcome is AdmissionOutcome.ALLOW
    assert decision.authority_class is AuthorityClass.DAEMON_RESTART
    assert decision.correlation_id == correlation
