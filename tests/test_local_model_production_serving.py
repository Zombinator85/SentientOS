from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlPlaneKernel
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_production_serving import ProductionServingController, ProductionServingError
from sentientos.local_model_runtime_worker import ExactRuntimeLocalModel
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.foreground_game_detection import ForegroundGameObservation
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (
    HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
    build_observation_plan,
)
from sentientos.runtime_governor import RuntimeGovernor

pytestmark = pytest.mark.no_legacy_skip


class Kernel:
    def __init__(self, outcome=AdmissionOutcome.ALLOW): self.outcome, self.requests = outcome, []
    def admit(self, request):
        self.requests.append(request)
        return SimpleNamespace(outcome=self.outcome, authority_class=request.authority_class, actor=request.actor,
            action_kind=request.action_kind, target_subsystem=request.target_subsystem,
            correlation_id=request.metadata["correlation_id"], admission_decision_ref="kernel_decision:" + request.metadata["correlation_id"])


class Model:
    def __init__(self, identity): self.active_identity, self.closed = identity, False
    def close(self): self.closed = True


def evidence(generation=1, *, gpu_layers=0):
    proof = {"proof_semantic_digest": "proof-digest", "deployment_receipt_id": "deployment-1"}
    state = {"installation_identity": "install-1", "generation": generation, "model_id": "model-1",
        "artifact_id": "artifact-1", "artifact_path": "/models/exact.gguf", "artifact_sha256": "a" * 64,
        "artifact_size_bytes": 42, "route_id": "route-1", "runtime_id": "runtime-1",
        "interpreter_path": "/runtime/python", "load_configuration": {
            "n_ctx": 1024, "n_gpu_layers": gpu_layers},
        "authority_map_digest": "authority-1", "commissioning_receipt_id": "commissioning-receipt-1",
        "commissioning_receipt_semantic_digest": "commissioning-digest"}
    state["state_semantic_digest"] = semantic_digest(state)
    prior = "ABSENT" if generation == 1 else semantic_digest({"prior_generation": generation - 1})
    activation = {"receipt_id": "activation-receipt-1", "receipt_semantic_digest": "activation-digest",
                  "resulting_state_digest": state["state_semantic_digest"],
                  "observed_prior_activation_state": prior, "expected_prior_activation_state": prior}
    history = [{"activation_receipt_id": activation["receipt_id"],
                "resulting_state_digest": state["state_semantic_digest"]}]
    return {"active_state": state, "activation_receipt": activation,
            "catalog_proof": proof, "activation_history": history}


@pytest.fixture
def handle(tmp_path):
    registry = InstallationStateRegistry(tmp_path / "custody", _test_only=True)
    return registry.open(InstallationIdentity.parse("install-1"), create=True)


def identity(**changes):
    values = dict(engine="llama_cpp", resolved_artifact_path="/models/exact.gguf",
        semantic_artifact_identity="sha256:" + "a" * 64, model_content_sha256="a" * 64,
        artifact_size_bytes=42, sidecar_metadata_digest=None, configuration_digest="config-1",
        candidate_index=0, posture="production", fallback=False)
    values.update(changes)
    return ActiveModelIdentity(**values)


def controller(monkeypatch, handle, sequence, kernel=None, factory=None):
    values = iter(sequence)
    monkeypatch.setattr("sentientos.local_model_production_serving.verify_current_activation", lambda *a, **k: next(values))
    result = ProductionServingController(handle, kernel or Kernel(), model_factory=factory or (lambda c, l: Model(identity())))
    monkeypatch.setattr(result, "_commissioning_identity", lambda s: identity().to_dict())
    return result


def test_success_loads_once_binds_receipt_and_performs_zero_inference(monkeypatch, handle):
    current = evidence(); made = []
    ctl = controller(monkeypatch, handle, [current, current, current], factory=lambda c, l: made.append(Model(identity())) or made[-1])
    session = ctl.establish(operation_id="serve-operation-1")
    assert len(made) == 1 and ctl.current_session() == session
    assert not hasattr(session, "generate") and not hasattr(session, "model")
    receipts = handle.list_regular_names(handle.fixed_object("local-model/serving/receipts"))
    receipt = __import__("json").loads(handle.read_regular(handle.fixed_object("local-model/serving/receipts/" + receipts[0])))
    assert receipt["model_loaded"] is True and receipt["serving_session_bound"] is True
    assert receipt["inference_performed"] is False and receipt["local_model_inference_authority_granted"] is False
    assert receipt["binding"]["serving_operation_id"] == "serve-operation-1"
    assert handle.list_regular_names(handle.fixed_object("logs/privileges"))


def test_failed_worker_close_preserves_exact_session_for_release_retry(monkeypatch, handle):
    current = evidence()
    model = Model(identity())
    close_calls = 0

    def close_once_fails():
        nonlocal close_calls
        close_calls += 1
        if close_calls == 1:
            raise RuntimeError("worker_shutdown_unconfirmed")
        model.closed = True

    model.close = close_once_fails
    ctl = controller(monkeypatch, handle, [current] * 3, factory=lambda c, l: model)
    session = ctl.establish(operation_id="serve-operation-retry-release")

    with pytest.raises(RuntimeError, match="worker_shutdown_unconfirmed"):
        ctl.release_current_session_after_resource_admission(
            session, reason="verified_game_host_pressure")

    assert ctl._session == session
    assert ctl._model is model
    invalidation_directory = handle.root / "local-model" / "serving" / "invalidations"
    assert not invalidation_directory.exists()

    assert ctl.release_current_session_after_resource_admission(
        session, reason="verified_game_host_pressure") is True
    assert model.closed is True
    assert ctl._session is None and ctl._model is None
    invalidations = handle.list_regular_names(
        handle.fixed_object("local-model/serving/invalidations"))
    assert len(invalidations) == 1


def test_resource_release_waits_for_exact_worker_exit_confirmation(monkeypatch, handle):
    current = evidence()
    model = Model(identity())
    poll_results = iter((None, 0))
    model._process = SimpleNamespace(poll=lambda: next(poll_results))
    ctl = controller(monkeypatch, handle, [current] * 3, factory=lambda c, l: model)
    session = ctl.establish(operation_id="serve-operation-exit-confirmation")

    with pytest.raises(ProductionServingError,
                       match="exact_runtime_worker_exit_unconfirmed"):
        ctl.release_current_session_after_resource_admission(
            session, reason="verified_game_host_pressure")

    assert ctl._session == session
    assert ctl._model is model

    assert ctl.release_current_session_after_resource_admission(
        session, reason="verified_game_host_pressure") is True
    assert ctl._session is None and ctl._model is None
    assert len(handle.list_regular_names(
        handle.fixed_object("local-model/serving/invalidations"))) == 1


def test_production_serving_release_closes_the_exact_runtime_process(monkeypatch, handle):
    process = subprocess.Popen(
        [sys.executable, "-u", "-c",
         "import sys, json\n"
         "print('ready', flush=True)\n"
         "for line in sys.stdin:\n"
         "    if json.loads(line).get('type') == 'shutdown':\n"
         "        print('shutdown', flush=True)\n"
         "        break\n"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)
    assert process.stdout is not None
    try:
        assert process.stdout.readline() == "ready\n"
        model = object.__new__(ExactRuntimeLocalModel)
        model._process = process
        model.active_identity = identity()
        ctl = controller(monkeypatch, handle, [evidence()] * 3,
                         factory=lambda _chain, _load: model)
        session = ctl.establish(operation_id="serve-operation-real-worker-release")

        assert process.poll() is None
        assert ctl.release_current_session_after_resource_admission(
            session, reason="verified_game_host_pressure") is True

        assert process.wait(timeout=2) == 0
        assert process.poll() == 0
        assert ctl.current_session() is None
        assert len(handle.list_regular_names(
            handle.fixed_object("local-model/serving/invalidations"))) == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


@pytest.mark.parametrize("outcome", [AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE])
def test_model_serving_admission_precedes_and_blocks_load(monkeypatch, handle, outcome):
    called = [] ; kernel = Kernel(outcome)
    ctl = controller(monkeypatch, handle, [evidence()], kernel=kernel, factory=lambda c, l: called.append(1))
    with pytest.raises(ProductionServingError, match="control_plane_not_allowed"): ctl.establish(operation_id="serve-operation-1")
    assert called == [] and ctl.current_session() is None
    assert kernel.requests[0].authority_class is AuthorityClass.MODEL_SERVING


@pytest.mark.parametrize(("gpu_value", "game_active", "gpu_layers", "workload_mode",
                         "should_load", "expected_reason"), [
    (94.0, True, 16, "automatic", False, "deferred_local_model_serving_under_host_pressure_during_game"),
    (20.0, True, 16, "automatic", False, "deferred_gpu_model_serving_while_game_active"),
    (20.0, False, 16, "automatic", True, "allowed"),
    (20.0, False, 16, "gaming", False, "deferred_gpu_model_serving_in_gaming_mode"),
    (20.0, False, 16, "conservative_automatic", False,
        "deferred_gpu_model_serving_in_conservative_automatic_mode"),
    ((None, 20.0), False, 16, "automatic", False, "deferred_gpu_offload_telemetry_incomplete"),
    ((20.0, None), False, 16, "automatic", False, "deferred_gpu_offload_telemetry_incomplete"),
    (None, True, 16, "automatic", False, "deferred_resource_telemetry_incomplete_during_game"),
    (20.0, True, 0, "automatic", True, "allowed"),
])
def test_runtime_governor_gates_initial_model_load_on_game_and_host_evidence(
        monkeypatch, handle, gpu_value, game_active, gpu_layers, workload_mode,
        should_load, expected_reason):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(handle.root / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(handle.root))
    now = datetime.now(timezone.utc)
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=handle.root / "kernel-decisions.jsonl")

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    def collect_gpu(*, observed_at=None):
        if gpu_value is None:
            return HostCollectorResult("nvidia_gpu", "unavailable",
                observed_at or now.isoformat(), "synthetic_test_fixture", values={})
        gpu_utilization, vram_utilization = (gpu_value if isinstance(gpu_value, tuple)
            else (gpu_value, gpu_value))
        return HostCollectorResult("nvidia_gpu", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture",
            values={"device_count": 1, "devices": [{"index": 0,
                "gpu_utilization_percent": gpu_utilization,
                "vram_utilization_percent": vram_utilization}]})

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=handle.root / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collect_gpu)
        ]), clock=lambda: now.isoformat())
    game = ForegroundGameObservation("available", game_active, "a" * 64, now.isoformat(),
        transport_provenance={"message_id": "b" * 64, "source_id": "windows-foreground",
            "session_id": "game-session", "generation_id": "game-generation",
            "sequence": 1, "envelope_created_at": now.isoformat()})
    assert kernel.observe_verified_game_workload(game)
    factory_calls: list[str] = []
    ctl = controller(monkeypatch, handle,
        [evidence(gpu_layers=gpu_layers), evidence(gpu_layers=gpu_layers)], kernel=kernel,
        factory=lambda _chain, _load: factory_calls.append("loaded") or Model(identity()))

    def admission_context(correlation_id, activation_state):
        observation_id = "local-chat-serving-" + hashlib.sha256(
            correlation_id.encode("utf-8")).hexdigest()[:32]
        host_owner.run_cycle(correlation_id=observation_id)
        load_configuration = activation_state["load_configuration"]
        conservative_automatic = workload_mode == "conservative_automatic"
        effective_mode = "gaming" if conservative_automatic else workload_mode
        return {
            "resource_governance_required": True,
            "purpose": "local_model_serving",
            "host_resource_observation_namespace": "local-chat-serving",
            "host_resource_observation_id": observation_id,
            "model_execution_profile": {
                "schema_version": "sentientos.model_execution_profile:v1",
                "engine": "llama_cpp",
                "accelerator_route": "gpu" if load_configuration["n_gpu_layers"] else "cpu",
                "gpu_layers": load_configuration["n_gpu_layers"],
                "configuration_digest": semantic_digest(load_configuration),
            },
            "workload_mode": effective_mode,
            "serving_workload_evidence": {
                "configured_mode": ("automatic" if conservative_automatic
                    else workload_mode),
                "mode_source": (
                    "foreground_observation_unavailable_conservative_gaming"
                    if conservative_automatic else
                    "operator_selected" if workload_mode == "gaming"
                    else "bridge_observed"),
                "observation_status": ("unavailable" if conservative_automatic
                    else "not_requested" if workload_mode == "gaming"
                    else "available"),
                "game_foreground": game_active,
                "game_process_running": game_active,
                "transport_provenance": (None if conservative_automatic
                    or workload_mode == "gaming" else {"message_id": "b" * 64}),
            },
        }

    if should_load:
        ctl.establish(operation_id="serve-operation-1",
            admission_context_provider=admission_context)
        assert factory_calls == ["loaded"]
        ctl.close()
        return
    with pytest.raises(ProductionServingError, match="control_plane_not_allowed"):
        ctl.establish(operation_id="serve-operation-1", admission_context_provider=admission_context)
    assert factory_calls == []
    decision = __import__("json").loads(
        (handle.root / "kernel-decisions.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    runtime = decision["delegated_outcomes"]["runtime_governor"]
    assert runtime["action_class"] == "local_model_serving"
    assert runtime["reason"] == expected_reason
    assert runtime["evidence_refs"]["host_resource_evidence"]["status"] == "current"
    if workload_mode in {"gaming", "conservative_automatic"}:
        assert runtime["evidence_refs"][
            "optional_gpu_model_load_in_gaming_profile"] is True
        expected_mode_source = (
            "foreground_observation_unavailable_conservative_gaming"
            if workload_mode == "conservative_automatic" else "operator_selected")
        assert runtime["evidence_refs"][
            "gaming_workload_profile_evidence"]["mode_source"] == (
                expected_mode_source)
    else:
        assert runtime["evidence_refs"]["game_workload_evidence"]["message_id"] == "b" * 64


@pytest.mark.parametrize(("transition", "expected_reason"), [
    ("game_started", "deferred_gpu_model_serving_while_game_active"),
    ("gaming_profile_selected", "deferred_gpu_model_serving_in_gaming_mode"),
])
def test_runtime_governor_revalidates_game_priority_after_gpu_model_load(
        monkeypatch, handle, transition, expected_reason):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(handle.root / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(handle.root / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(handle.root))
    now = datetime.now(timezone.utc)
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=handle.root / "kernel-decisions.jsonl")

    def observation(active, message_id, sequence):
        return ForegroundGameObservation("available", active, "a" * 64,
            now.isoformat(), transport_provenance={
                "message_id": message_id, "source_id": "windows-foreground",
                "session_id": "game-session", "generation_id": "game-generation",
                "sequence": sequence, "envelope_created_at": now.isoformat()})

    idle_game = observation(False, "b" * 64, 1)
    active_game = observation(True, "c" * 64, 2)
    assert kernel.observe_verified_game_workload(idle_game)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=handle.root / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 20.0,
                    "vram_utilization_percent": 30.0}]))
        ]), clock=lambda: now.isoformat())
    model = Model(identity())
    current = evidence(gpu_layers=16)
    latest_game = {"observation": idle_game}
    latest_mode = {"mode": "automatic" if transition == "game_started" else "normal"}

    def load_model(_chain, _load):
        if transition == "game_started":
            latest_game["observation"] = active_game
            assert kernel.observe_verified_game_workload(active_game)
        else:
            latest_mode["mode"] = "gaming"
        return model

    ctl = controller(monkeypatch, handle, [current] * 4, kernel=kernel,
        factory=load_model)

    def admission_context(correlation_id, activation_state):
        observation_id = "local-chat-serving-" + hashlib.sha256(
            correlation_id.encode("utf-8")).hexdigest()[:32]
        assert host_owner.run_cycle(correlation_id=observation_id) is not None
        game = latest_game["observation"]
        mode = latest_mode["mode"]
        load_configuration = activation_state["load_configuration"]
        return {
            "resource_governance_required": True,
            "purpose": "local_model_serving",
            "host_resource_observation_namespace": "local-chat-serving",
            "host_resource_observation_id": observation_id,
            "workload_mode": mode,
            "model_execution_profile": {
                "schema_version": "sentientos.model_execution_profile:v1",
                "engine": "llama_cpp", "accelerator_route": "gpu",
                "gpu_layers": 16,
                "configuration_digest": semantic_digest(load_configuration),
            },
            "serving_workload_evidence": {
                "configured_mode": mode,
                "mode_source": ("operator_selected" if mode == "gaming"
                    else "bridge_observed" if mode == "automatic"
                    else "operator_selected"),
                "observation_status": ("not_requested" if mode == "gaming"
                    else "available" if mode == "automatic" else "not_requested"),
                "game_foreground": (game.game_foreground
                    if mode == "automatic" else False),
                "game_process_running": (game.game_process_running
                    if mode == "automatic" else False),
                "transport_provenance": (game.transport_provenance
                    if mode == "automatic" else None),
            },
        }

    with pytest.raises(ProductionServingError,
            match="model_serving_resource_policy_changed_during_load"):
        ctl.establish(operation_id="serving-game-started-during-load",
            admission_context_provider=admission_context)

    assert model.closed is True
    assert ctl.current_session() is None
    decisions = [__import__("json").loads(line) for line in
        (handle.root / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
    serving_decisions = [item for item in decisions
        if item.get("authority_class") == AuthorityClass.MODEL_SERVING.value]
    assert [item["final_disposition"] for item in serving_decisions] == ["allow", "defer"]
    assert serving_decisions[0]["correlation_id"] != serving_decisions[1]["correlation_id"]
    assert serving_decisions[1]["delegated_outcomes"]["runtime_governor"]["reason"] == (
        expected_reason)
    runtime_evidence = serving_decisions[1]["delegated_outcomes"][
        "runtime_governor"]["evidence_refs"]
    if transition == "game_started":
        assert runtime_evidence["game_workload_evidence"]["message_id"] == "c" * 64
    else:
        assert runtime_evidence[
            "optional_gpu_model_load_in_gaming_profile"] is True
    assert host_owner.collector_call_count == 6
    from sentientos.local_model_production_serving import read_serving_operation_history
    assert read_serving_operation_history(handle)[0]["status"] == (
        "reservation_outcome_unknown")
    with pytest.raises(ProductionServingError, match="serving_operation_reused"):
        ctl.establish(operation_id="serving-game-started-during-load",
            admission_context_provider=admission_context)
    assert len([item for item in
        read_serving_operation_history(handle)]) == 1


def test_observed_identity_mismatch_closes_without_bind(monkeypatch, handle):
    model = Model(identity(engine="substituted")); ctl = controller(monkeypatch, handle, [evidence()], factory=lambda c, l: model)
    with pytest.raises(ProductionServingError, match="observed_identity_mismatch"): ctl.establish(operation_id="serve-operation-1")
    assert model.closed and ctl.current_session() is None


def test_activation_change_during_load_closes_before_bind(monkeypatch, handle):
    model = Model(identity()); ctl = controller(monkeypatch, handle, [evidence(1), evidence(2)], factory=lambda c, l: model)
    with pytest.raises(ProductionServingError, match="activation_changed_during_load"): ctl.establish(operation_id="serve-operation-1")
    assert model.closed and ctl.current_session() is None


def test_activation_change_after_bind_invalidates_and_unloads(monkeypatch, handle):
    model = Model(identity()); one, two = evidence(1), evidence(2)
    ctl = controller(monkeypatch, handle, [one, one, two], factory=lambda c, l: model)
    ctl.establish(operation_id="serve-operation-1")
    assert ctl.current_session() is None and model.closed
    assert handle.list_regular_names(handle.fixed_object("local-model/serving/invalidations"))


def test_dead_worker_is_not_current(monkeypatch, handle):
    model = Model(identity()); model._process = SimpleNamespace(poll=lambda: 7)
    current = evidence(); ctl = controller(monkeypatch, handle, [current, current, current], factory=lambda c, l: model)
    ctl.establish(operation_id="serve-operation-1")
    assert ctl.current_session() is None and model.closed


def test_read_only_currentness_reports_activation_change_without_invalidation(monkeypatch, handle):
    model = Model(identity()); one, two = evidence(1), evidence(2)
    ctl = controller(monkeypatch, handle, [one, one, two], factory=lambda c, l: model)
    ctl.establish(operation_id="serve-operation-1")
    assert ctl.serving_is_current() is False
    assert model.closed is False
    assert not (handle.root / "local-model" / "serving" / "invalidations").exists()


def test_read_only_currentness_reports_dead_worker_without_invalidation(monkeypatch, handle):
    model = Model(identity()); current = evidence()
    ctl = controller(monkeypatch, handle, [current, current, current], factory=lambda c, l: model)
    ctl.establish(operation_id="serve-operation-1")
    model._process = SimpleNamespace(poll=lambda: 7)
    assert ctl.serving_is_current() is False
    assert model.closed is False
    assert not (handle.root / "local-model" / "serving" / "invalidations").exists()


def test_constructor_has_no_path_runtime_or_preloaded_model_parameters():
    import inspect
    parameters = inspect.signature(ProductionServingController).parameters
    assert not {"model_path", "activation_path", "runtime", "preloaded_model", "autoload"} & set(parameters)

@pytest.mark.parametrize("operation_id", ["", " ", "*", "latest", "placeHolder", "op?", " op", "op ", "x" * 129])
def test_invalid_serving_operation_identity_is_rejected_before_activation(monkeypatch, handle, operation_id):
    monkeypatch.setattr("sentientos.local_model_production_serving.verify_current_activation",
                        lambda *a, **k: pytest.fail("activation must not be read"))
    ctl = ProductionServingController(handle, Kernel(), model_factory=lambda c, l: pytest.fail("must not load"))
    with pytest.raises(ProductionServingError, match="serving_operation_id_invalid"):
        ctl.establish(operation_id=operation_id)


def test_current_session_is_reused_without_second_load_and_operation_is_audited(monkeypatch, handle):
    current, made, kernel = evidence(), [], Kernel()
    ctl = controller(monkeypatch, handle, [current] * 6, kernel=kernel,
                     factory=lambda c, l: made.append(Model(identity())) or made[-1])
    first = ctl.establish(operation_id="serve-operation-1")
    with pytest.raises(ProductionServingError, match="current_serving_operation_mismatch"):
        ctl.establish(operation_id="serve-operation-2")
    assert ctl.current_session() == first
    assert len(made) == 1 and len(kernel.requests) == 1
    metadata = kernel.requests[0].metadata
    assert metadata["serving_operation_id"] == "serve-operation-1"
    assert metadata["correlation_id"] == first.binding["control_plane_correlation_id"]


def test_correlations_bind_operation_and_activation(monkeypatch, handle):
    one, two, kernel = evidence(1), evidence(2), Kernel()
    ctl = controller(monkeypatch, handle, [one, one, one, one, two, two], kernel=kernel)
    first = ctl.establish(operation_id="serve-operation-1")
    ctl.close()
    second = ctl.establish(operation_id="serve-operation-2")
    ctl.close()
    third = ctl.establish(operation_id="serve-operation-3")
    correlations = [request.metadata["correlation_id"] for request in kernel.requests]
    assert len(set(correlations)) == 3
    assert len({first.session_id, second.session_id, third.session_id}) == 3


def test_real_kernel_dedupes_replay_but_admits_new_operation_for_same_activation(monkeypatch, handle, tmp_path):
    current, made = evidence(), []
    kernel = ControlPlaneKernel(decisions_path=tmp_path / "kernel-decisions.jsonl")
    ctl = controller(monkeypatch, handle, [current] * 6, kernel=kernel,
                     factory=lambda c, l: made.append(Model(identity())) or made[-1])
    first = ctl.establish(operation_id="serve-operation-1")
    ctl.close()
    with pytest.raises(ProductionServingError, match="serving_operation_reused"):
        ctl.establish(operation_id="serve-operation-1")
    assert len(made) == 1
    second = ctl.establish(operation_id="serve-operation-2")
    assert len(made) == 2 and first.session_id != second.session_id
    receipts = [__import__("json").loads(handle.read_regular(handle.fixed_object("local-model/serving/receipts/" + name)))
                for name in handle.list_regular_names(handle.fixed_object("local-model/serving/receipts"))]
    assert len({receipt["receipt_id"] for receipt in receipts}) == 2
    assert all(receipt["inference_performed"] is False for receipt in receipts)
    assert all(receipt["local_model_inference_authority_granted"] is False for receipt in receipts)


def test_same_activation_operation_replay_blocked_across_fresh_controllers(monkeypatch, handle, tmp_path):
    current, made = evidence(), []
    monkeypatch.setattr("sentientos.local_model_production_serving.verify_current_activation",
                        lambda *a, **k: current)
    first = ProductionServingController(handle, ControlPlaneKernel(decisions_path=tmp_path / "one.jsonl"),
        model_factory=lambda c, l: made.append(Model(identity())) or made[-1])
    second = ProductionServingController(handle, ControlPlaneKernel(decisions_path=tmp_path / "two.jsonl"),
        model_factory=lambda c, l: made.append(Model(identity())) or made[-1])
    monkeypatch.setattr(first, "_commissioning_identity", lambda s: identity().to_dict())
    monkeypatch.setattr(second, "_commissioning_identity", lambda s: identity().to_dict())
    first.establish(operation_id="serve-operation-X"); first.close()
    with pytest.raises(ProductionServingError, match="serving_operation_reused"):
        second.establish(operation_id="serve-operation-X")
    assert len(made) == 1
    second.establish(operation_id="serve-operation-Y")
    assert len(made) == 2


@pytest.mark.parametrize("cause", ["worker_death", "controller_close"])
def test_new_operation_reestablishes_distinct_lifetime(monkeypatch, handle, cause):
    current, made = evidence(), []
    ctl = controller(monkeypatch, handle, [current] * 6,
                     factory=lambda c, l: made.append(Model(identity())) or made[-1])
    first = ctl.establish(operation_id="serve-operation-1")
    if cause == "worker_death":
        made[0]._process = SimpleNamespace(poll=lambda: 7)
        assert ctl.current_session() is None
    else:
        ctl.close()
    second = ctl.establish(operation_id="serve-operation-2")
    assert len(made) == 2 and first.session_id != second.session_id
    ctl.close()
    invalidations = [__import__("json").loads(handle.read_regular(handle.fixed_object("local-model/serving/invalidations/" + name)))
                     for name in handle.list_regular_names(handle.fixed_object("local-model/serving/invalidations"))]
    assert len({item["invalidation_id"] for item in invalidations}) == 2
    assert {(item["session_id"], item["serving_operation_id"]) for item in invalidations} == {
        (first.session_id, "serve-operation-1"), (second.session_id, "serve-operation-2")}


def test_authenticated_game_evidence_gates_actual_serving_load_until_idle(
        monkeypatch, handle, tmp_path):
    """Authenticated game entry blocks the exact model factory until fresh idle evidence."""
    import json
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from sentientos.foreground_game_bridge import (
        BridgeForegroundGameDetector, WindowsForegroundBridgePublisher,
    )
    from sentientos.foreground_game_detection import ForegroundGameDetector
    from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
    from sentientos.gaming_companion_tls_transport import (
        CompanionBridgeMutualTLSClient, CompanionBridgeMutualTLSRuntime,
    )
    from sentientos.host_resource_runtime import HostObservationCollectorSpec
    from tests.test_gaming_companion_tls_transport import _certificate_bundle

    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(handle.root / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(handle.root))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=handle.root / "kernel-decisions.jsonl")
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate(
        (tmp_path / "server.pem").read_bytes())
    source_key, acknowledgment_key = b"p" * 32, b"q" * 32
    source_id, generation_id = "windows-edge", "serving-load-generation-1"
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1", port=0,
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="serving-core-generation-1",
        acknowledgment_key=acknowledgment_key)
    port = runtime.start()
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": acknowledgment_key},
            expected_generations={"wsl-core": "serving-core-generation-1"}),
        expected_server_certificate_sha256=hashlib.sha256(
            server_certificate.public_bytes(Encoding.DER)).hexdigest())
    foreground = {"game": True}
    publisher = WindowsForegroundBridgePublisher(
        detector=ForegroundGameDetector(system_provider=lambda: "Windows",
            process_name_provider=lambda: ("ExampleGame.exe" if foreground["game"]
                else "explorer.exe"),
            running_process_names_provider=lambda: (
                ("ExampleGame.exe",) if foreground["game"] else ()),
            clock=lambda: now.isoformat()),
        client=client, source_id=source_id, session_id="serving-load-game-session",
        generation_id=generation_id, source_key=source_key)
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=source_id,
        generation_id=generation_id, clock=lambda: now)
    detector.set_game_workload_admission_owner(kernel)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=handle.root / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 10.0,
                    "vram_utilization_percent": 20.0}])),
        ]), clock=lambda: now.isoformat())
    factory_calls = []
    model = Model(identity())
    current = evidence(gpu_layers=16)
    ctl = controller(monkeypatch, handle, [current, current, current, current], kernel=kernel,
        factory=lambda _chain, _load: factory_calls.append("loaded") or model)

    def admission_context(correlation_id, activation_state):
        observation_id = "local-chat-serving-" + hashlib.sha256(
            correlation_id.encode("utf-8")).hexdigest()[:32]
        host_owner.run_cycle(correlation_id=observation_id)
        workload = detector.observe(("ExampleGame.exe",))
        load_configuration = activation_state["load_configuration"]
        return {
            "resource_governance_required": True,
            "purpose": "local_model_serving",
            "host_resource_observation_namespace": "local-chat-serving",
            "host_resource_observation_id": observation_id,
            "workload_mode": "automatic",
            "model_execution_profile": {
                "schema_version": "sentientos.model_execution_profile:v1",
                "engine": "llama_cpp", "accelerator_route": "gpu",
                "gpu_layers": load_configuration["n_gpu_layers"],
                "configuration_digest": semantic_digest(load_configuration),
            },
            "serving_workload_evidence": {
                "configured_mode": "automatic",
                "observation_status": workload.status,
                "game_foreground": workload.game_foreground,
                "game_process_running": workload.game_process_running,
                "transport_provenance": workload.transport_provenance,
            },
        }

    try:
        active_message = publisher.publish_once(("ExampleGame.exe",))
        with pytest.raises(ProductionServingError, match="control_plane_not_allowed"):
            ctl.establish(operation_id="serving-game-active",
                admission_context_provider=admission_context)
        assert factory_calls == []
        assert ctl.current_session() is None

        foreground["game"] = False
        idle_message = publisher.publish_once(("ExampleGame.exe",))
        session = ctl.establish(operation_id="serving-game-idle",
            admission_context_provider=admission_context)
        assert factory_calls == ["loaded"]
        assert ctl.current_session() == session

        decisions = [json.loads(line) for line in
            (handle.root / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines()]
        serving_decisions = [item for item in decisions
            if item.get("authority_class") == AuthorityClass.MODEL_SERVING.value]
        assert [item["final_disposition"] for item in serving_decisions] == [
            "defer", "allow", "allow"]
        assert serving_decisions[0]["delegated_outcomes"]["runtime_governor"][
            "reason"] == "deferred_gpu_model_serving_while_game_active"
        assert serving_decisions[0]["delegated_outcomes"]["runtime_governor"][
            "evidence_refs"]["game_workload_evidence"]["message_id"] == (
                active_message.payload["message_id"])
        assert serving_decisions[1]["delegated_outcomes"]["runtime_governor"][
            "evidence_refs"]["game_workload_evidence"]["message_id"] == (
                idle_message.payload["message_id"])
        assert serving_decisions[2]["delegated_outcomes"]["runtime_governor"][
            "evidence_refs"]["game_workload_evidence"]["message_id"] == (
                idle_message.payload["message_id"])
        assert session.binding["resource_admission_revalidation_correlation_id"] == (
            serving_decisions[2]["correlation_id"])
        assert session.binding["resource_admission_revalidation_decision_ref"] == (
            serving_decisions[2]["admission_decision_ref"])
        assert host_owner.collector_call_count == 9
    finally:
        ctl.close()
        detector.close()
