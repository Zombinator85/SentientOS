from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from sentientos import local_model_production_serving as serving
from sentientos.control_plane_kernel import (AdmissionOutcome, AuthorityClass,
                                              ControlActionRequest, ControlPlaneKernel,
                                              LifecyclePhase)
from sentientos.federated_governance import reset_controller as reset_federated_governance_controller
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_production_serving import ProductionServingController
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.runtime_governor import reset_runtime_governor
from sentientos.trust_ledger import reset_trust_ledger
from sentientos.runtime.local_model_chat_recovery import (
    LocalModelChatRecoveryError,
    ProductionLocalModelChatRecoveryController,
    build_recovery_intent,
    build_startup_snapshot,
    require_fresh_operation,
    verify_approval,
    verified_serving_receipts,
    write_startup_snapshot,
)
from sentientos.runtime.local_model_chat_service import LocalModelChatServiceAdapter, LocalModelChatStartup

pytestmark = pytest.mark.no_legacy_skip


def activation() -> dict:
    state = {"installation_identity": "install-1", "generation": 1, "model_id": "model-1",
        "artifact_id": "artifact-1", "artifact_path": "/models/exact.gguf",
        "artifact_sha256": "a" * 64, "artifact_size_bytes": 42, "route_id": "route-1",
        "runtime_id": "runtime-1", "interpreter_path": "/runtime/python",
        "load_configuration": {"n_ctx": 1024, "n_gpu_layers": 0},
        "authority_map_digest": "map-1", "commissioning_receipt_id": "commissioning-1",
        "commissioning_receipt_semantic_digest": "commissioning-digest"}
    state["state_semantic_digest"] = semantic_digest(state)
    prior = "ABSENT"
    receipt = {"receipt_id": "activation-1", "receipt_semantic_digest": "activation-digest",
        "resulting_state_digest": state["state_semantic_digest"],
        "observed_prior_activation_state": prior, "expected_prior_activation_state": prior}
    return {"active_state": state, "activation_receipt": receipt,
        "catalog_proof": {"proof_semantic_digest": "proof-digest", "deployment_receipt_id": "deployment-1"},
        "activation_history": ({"activation_receipt_id": receipt["receipt_id"],
            "activation_receipt_semantic_digest": receipt["receipt_semantic_digest"],
            "resulting_state_digest": state["state_semantic_digest"]},)}


def receipt(operation: str = "serve-1") -> dict:
    current = activation()
    state, activation_receipt = current["active_state"], current["activation_receipt"]
    provenance = {"activation_state_semantic_digest": state["state_semantic_digest"],
        "activation_generation": state["generation"],
        "activation_receipt_id": activation_receipt["receipt_id"],
        "activation_receipt_semantic_digest": activation_receipt["receipt_semantic_digest"],
        "model_id": state["model_id"], "artifact_id": state["artifact_id"],
        "runtime_id": state["runtime_id"], "authority_map_digest": state["authority_map_digest"]}
    value = {"schema_version": "sentientos.local_model_serving_session_receipt:v1",
        "receipt_id": "receipt-" + operation, "session_id": "session-" + operation,
        "binding": {"installation_identity": "install-1", "serving_operation_id": operation, **provenance},
        "control_plane_authority_class": "model_serving", "admission_outcome": "allow",
        "model_loaded": True, "serving_session_bound": True, "inference_performed": False}
    value["receipt_semantic_digest"] = semantic_digest(value)
    return value


def snapshot() -> dict:
    return build_startup_snapshot(LocalModelChatStartup(True, "install-1", "serve-1"), "generation-1")


class _ServingKernel:
    def __init__(self) -> None:
        self.requests = []

    def admit(self, request):
        self.requests.append(request)
        return SimpleNamespace(outcome=AdmissionOutcome.ALLOW,
            authority_class=request.authority_class, actor=request.actor,
            action_kind=request.action_kind, target_subsystem=request.target_subsystem,
            correlation_id=request.metadata["correlation_id"], admission_decision_ref="test-serving-admission")


def _active_model_identity() -> ActiveModelIdentity:
    return ActiveModelIdentity(engine="llama_cpp", resolved_artifact_path="/models/exact.gguf",
        semantic_artifact_identity="sha256:" + "a" * 64, model_content_sha256="a" * 64,
        artifact_size_bytes=42, sidecar_metadata_digest=None, configuration_digest="config-1",
        candidate_index=0, posture="production", fallback=False)


def _publish_serving_receipt(handle, operation: str, monkeypatch) -> dict:
    evidence = activation()
    monkeypatch.setattr(serving, "verify_current_activation", lambda *_a, **_k: evidence)
    controller = ProductionServingController(handle, _ServingKernel(),
        model_factory=lambda *_a: SimpleNamespace(active_identity=_active_model_identity(), close=lambda: None))
    monkeypatch.setattr(controller, "_commissioning_identity", lambda _state: _active_model_identity().to_dict())
    controller.establish(operation_id=operation)
    matching = [item for item in verified_serving_receipts(handle)
                if item["binding"]["serving_operation_id"] == operation]
    assert len(matching) == 1
    controller.close()
    return matching[0]


def _running_handoff_adapter(tmp_path: Path, handle, operation: str, monkeypatch):
    """Launch a real child and exercise the installation-backed parent/child handoff verifier."""
    root = tmp_path / "runtime-source"
    (root / "sentientos").mkdir(parents=True)
    scripts = root / "scripts"
    scripts.mkdir()
    result_path, release_path = tmp_path / "child-result.json", tmp_path / "release-child"
    monkeypatch.setenv("TEST_REGISTRY_ROOT", str(handle._registry._base))
    monkeypatch.setenv("TEST_CHILD_RESULT", str(result_path))
    monkeypatch.setenv("TEST_RELEASE_CHILD", str(release_path))
    (scripts / "local_model_chat.py").write_text("""\\
import json, os, sys, time
from pathlib import Path
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.chat_process_generation import verify_current_chat_process_handoff
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
registry = InstallationStateRegistry._for_testing(Path(os.environ['TEST_REGISTRY_ROOT']))
handle = registry.open(InstallationIdentity.parse(args['--installation-identity']))
deadline = time.monotonic() + 5
while True:
    try:
        handoff = verify_current_chat_process_handoff(handle=handle, handoff_id=args['--runtime-handoff-id'])
        break
    except Exception:
        if time.monotonic() >= deadline:
            raise
        time.sleep(.01)
Path(os.environ['TEST_CHILD_RESULT']).write_text(json.dumps(handoff, sort_keys=True))
deadline = time.monotonic() + 20
while not Path(os.environ['TEST_RELEASE_CHILD']).exists() and time.monotonic() < deadline:
    time.sleep(.01)
""", encoding="utf-8")
    adapter = LocalModelChatServiceAdapter(
        LocalModelChatStartup(True, handle.identity.value, operation, port=5500),
        probe=lambda _url: True, installation_handle=handle)
    adapter._root = root
    adapter._cwd = root
    package_root = Path(__file__).resolve().parents[1]
    adapter._launch_environment["PYTHONPATH"] = os.pathsep.join((str(package_root), str(root)))
    adapter._environment = dict(adapter._launch_environment)
    adapter.start()
    deadline = time.monotonic() + 5
    while not result_path.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert result_path.exists(), bytes(adapter._diagnostics).decode("utf-8", "replace")
    child = json.loads(result_path.read_text(encoding="utf-8"))
    parent = adapter.current_runtime_handoff()
    assert child["process_instance_id"] == parent["process_instance_id"]
    assert child["software_generation_digest"] == parent["software_generation_digest"]
    return adapter, release_path


def test_approved_unchanged_activation_recovery_intent_is_deterministic_and_zero_inference() -> None:
    arguments = dict(snapshot=snapshot(), prior_receipt=receipt(), activation=activation(),
                     replacement_serving_operation_id="serve-2", recovery_correlation_id="recover-1")
    first = build_recovery_intent(**arguments)
    assert first == build_recovery_intent(**arguments)
    assert first["runtime_supervisor_generation"] == "generation-1"
    assert first["startup_configuration_digest"] == snapshot()["startup_configuration_digest"]
    assert first["prior_serving_receipt_semantic_digest"] == receipt()["receipt_semantic_digest"]
    assert first["activation_state_semantic_digest"] == activation()["active_state"]["state_semantic_digest"]
    assert first["recovery_inference"] is False


@pytest.mark.parametrize("replacement", ["", "*", "latest", "serve-1"])
def test_replacement_operation_must_be_nonplaceholder_and_different(replacement: str) -> None:
    with pytest.raises((LocalModelChatRecoveryError, RuntimeError)):
        build_recovery_intent(snapshot=snapshot(), prior_receipt=receipt(), activation=activation(),
            replacement_serving_operation_id=replacement, recovery_correlation_id="recover-1")


def test_globally_fresh_replacement_operation_rejects_any_older_lifetime(tmp_path: Path) -> None:
    handle = InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("install-1"), create=True)
    with pytest.MonkeyPatch.context() as monkeypatch:
        old = _publish_serving_receipt(handle, "serve-old", monkeypatch)
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
    observed = activation()
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


def test_restart_preserves_resource_provisioning_identity(monkeypatch) -> None:
    adapter = LocalModelChatServiceAdapter(LocalModelChatStartup(
        True, "install-1", "serve-1", port=5500, resource_provisioning_id="production.v1"))
    monkeypatch.setattr(adapter, "stop", lambda: None)
    monkeypatch.setattr("sentientos.runtime.services.ChildProcessServiceAdapter.start", lambda _self: None)
    adapter._restart_with_fresh_serving_operation(replacement_serving_operation_id="serve-2",
                                                   expected_activation_state_digest="a" * 64)
    assert adapter.startup_configuration.resource_provisioning_id == "production.v1"
    assert adapter._argv[-2:] == ("--resource-provisioning-id", "production.v1")


def test_recovery_surface_has_no_generic_process_or_model_escape() -> None:
    parameters = set(inspect.signature(LocalModelChatServiceAdapter._restart_with_fresh_serving_operation).parameters)
    assert parameters == {"self", "replacement_serving_operation_id", "expected_activation_state_digest"}
    forbidden = {"argv", "executable", "script", "model", "backend", "runtime_path", "activation_path"}
    assert not parameters & forbidden


def test_daemon_restart_independent_admission_uses_real_control_plane_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The real governor bootstraps trust-epoch custody as part of admission.
    # Keep that test-owned persistence local rather than depending on host
    # /glow permissions or ambient state.
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_CONTROL_KERNEL_ROOT", str(tmp_path / "control-kernel"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "pulse-trust"))
    monkeypatch.setenv(
        "PULSE_TRUST_EPOCH_STATE", str(tmp_path / "pulse-trust" / "epoch_state.json")
    )
    reset_federated_governance_controller()
    reset_trust_ledger()
    reset_runtime_governor()
    correlation = "local-model-chat-recovery:integration-1"
    decision = ControlPlaneKernel(decisions_path=tmp_path / "decisions.jsonl").admit(ControlActionRequest(
        action_kind="restart_daemon", authority_class=AuthorityClass.DAEMON_RESTART,
        actor="deterministic_local_model_chat_recovery_controller",
        target_subsystem="local_model_chat", requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": correlation, "subject": "local_model_chat", "recovery_scope": "local"}))
    assert decision.outcome is AdmissionOutcome.ALLOW
    assert decision.authority_class is AuthorityClass.DAEMON_RESTART
    assert decision.correlation_id == correlation


def approval_for(intent: dict, **changes) -> dict:
    value = {"schema_version": "sentientos.local_model_chat_recovery_approval:v1",
        "approval_status": "approved", "operator_identity": "operator:alice",
        "evidence_id": "approval-1", "evidence_source": "operator-console",
        "evidence_provenance": "signed-local-approval", "synthetic_test_evidence": False,
        "not_before": "2026-01-01T00:00:00+00:00", "approved_at": "2026-01-01T00:01:00+00:00",
        "expires_at": "2026-01-01T01:00:00+00:00",
        "intent_id": intent["intent_id"], "intent_semantic_digest": intent["intent_semantic_digest"],
        "installation_identity": intent["installation_identity"],
        "runtime_supervisor_generation": intent["runtime_supervisor_generation"],
        "prior_serving_operation_id": intent["prior_serving_operation_id"],
        "replacement_serving_operation_id": intent["replacement_serving_operation_id"],
        "expected_activation_state_digest": intent["activation_state_semantic_digest"],
        "recovery_correlation_id": intent["recovery_correlation_id"]}
    value.update(changes)
    value["approval_semantic_digest"] = semantic_digest(
        {key: item for key, item in value.items() if key != "approval_semantic_digest"})
    return value


@pytest.mark.parametrize("change,code", [
    ({"approved_at": "2026-01-01T00:01:00"}, "time_invalid"),
    ({"not_before": "2026-01-01T00:02:00+00:00"}, "interval_invalid"),
    ({"evidence_provenance": ""}, "provenance_invalid"),
    ({"synthetic_test_evidence": True}, "synthetic_recovery_approval_forbidden"),
    ({"synthetic_test_evidence": None}, "synthetic_recovery_approval_forbidden"),
])
def test_recovery_approval_temporal_and_provenance_hardening(change, code) -> None:
    intent = build_recovery_intent(snapshot=snapshot(), prior_receipt=receipt(), activation=activation(),
        replacement_serving_operation_id="serve-2", recovery_correlation_id="recover-1")
    with pytest.raises(LocalModelChatRecoveryError, match=code):
        verify_approval(approval_for(intent, **change), intent, now=1767227400.0)


@pytest.mark.parametrize("outcome", [AdmissionOutcome.ALLOW, AdmissionOutcome.DENY,
                                      AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE])
def test_full_recovery_controller_transaction_and_denials(monkeypatch, tmp_path: Path, outcome) -> None:
    handle = InstallationStateRegistry._for_testing(tmp_path / "custody").open(
        InstallationIdentity("install-1"), create=True)
    prior = _publish_serving_receipt(handle, "serve-1", monkeypatch)
    adapter, release_path = _running_handoff_adapter(tmp_path, handle, "serve-1", monkeypatch)
    root = tmp_path / "runtime"
    handoff = adapter.current_runtime_handoff()
    snap = build_startup_snapshot(adapter.startup_configuration, "generation-1", runtime_handoff=handoff)
    write_startup_snapshot(snap, root)
    intent = build_recovery_intent(snapshot=snap, prior_receipt=prior, activation=activation(),
        replacement_serving_operation_id="serve-2", recovery_correlation_id="recover-1")
    approval = approval_for(intent)
    request = {"schema_version": "sentientos.local_model_chat_recovery_request:v1",
               "intent": intent, "approval": approval, "inference_performed": False}
    request["request_id"] = "local-model-chat-recovery-request-" + semantic_digest(request)[:24]
    request["request_semantic_digest"] = semantic_digest(request)
    request_dir = handle.fixed_object("local-model/recovery/requests"); handle.ensure_directory(request_dir)
    handle.durable_create(request_dir.child(request["request_id"] + ".json"),
        (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode())
    supervisor = SimpleNamespace(root=root, generation="generation-1",
        status=lambda: {"generation": "generation-1", "state": "running",
                        "services": {"local_model_chat": {"state": "unhealthy"}}},
        _observe_explicit_recovery=lambda _service: "healthy")
    restarts = []
    real_start = adapter.start
    def start_with_serving_receipt():
        real_start()
        if adapter.startup_configuration.serving_operation_id == "serve-2":
            _publish_serving_receipt(handle, "serve-2", monkeypatch)
    monkeypatch.setattr(adapter, "start", start_with_serving_receipt)
    real_restart = adapter._restart_with_fresh_serving_operation
    def record_restart(**kwargs):
        restarts.append(kwargs)
        return real_restart(**kwargs)
    monkeypatch.setattr(adapter, "_restart_with_fresh_serving_operation", record_restart)
    monkeypatch.setattr("sentientos.runtime.local_model_chat_recovery._current_activation", lambda _handle: activation())
    kernel = SimpleNamespace(requests=[])
    def admit(control_request):
        kernel.requests.append(control_request)
        return SimpleNamespace(outcome=outcome, authority_class=control_request.authority_class,
            actor=control_request.actor, action_kind=control_request.action_kind,
            target_subsystem=control_request.target_subsystem,
            correlation_id=control_request.metadata["correlation_id"], admission_decision_ref="decision-1")
    kernel.admit = admit
    ctl = ProductionLocalModelChatRecoveryController(supervisor, adapter, kernel, handle,
        clock=lambda: 1767227400.0)
    try:
        result = ctl.process_request(request["request_id"] + ".json")
        assert len(kernel.requests) == 1
        assert kernel.requests[0].authority_class is AuthorityClass.DAEMON_RESTART
        assert kernel.requests[0].actor == "deterministic_local_model_chat_recovery_controller"
        assert kernel.requests[0].target_subsystem == "local_model_chat"
        if outcome is AdmissionOutcome.ALLOW:
            assert result["terminal_status"] == "recovered" and len(restarts) == 1
            assert result["model_serving_granted_by_recovery"] is False
            assert result["inference_performed"] is False
            assert result["local_model_inference_authority_granted"] is False
            assert result["predecessor_chat_process_handoff"] == handoff
            successor_handoff = result["successor_chat_process_handoff"]
            assert successor_handoff["handoff_id"] != handoff["handoff_id"]
            assert successor_handoff["process_instance_id"] != handoff["process_instance_id"]
            assert result["successor_serving_receipt_id"] is not None
            assert ctl.process_request(request["request_id"] + ".json") == result
            assert ctl.process_pending() == (result,)
            assert len(kernel.requests) == 1 and len(restarts) == 1
        else:
            assert result["terminal_status"] == "failed" and restarts == []
            assert result["daemon_restart_outcome"] == outcome.value
            assert result["child_restart_attempted"] is False
            assert not [item for item in verified_serving_receipts(handle)
                       if item["binding"]["serving_operation_id"] == "serve-2"]
    finally:
        release_path.write_text("release\n", encoding="utf-8")
        adapter.stop()
