from __future__ import annotations

import asyncio
import inspect
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos import chat_service
from sentientos.ops import __main__ as ops
from sentientos.runtime.local_model_chat_service import (
    SERVICE_ID,
    LocalModelChatServiceAdapter,
    LocalModelChatStartup,
    build_runtime_service_registry,
)
from sentientos.runtime.services import HealthResult, InProcessServiceAdapter
from sentientos.runtime.startup import run_canonical_runtime
from sentientos.runtime.supervisor import RuntimeServiceDescriptor, RuntimeSupervisor, ServiceRegistry

pytestmark = pytest.mark.no_legacy_skip


def test_disabled_registration_has_zero_production_or_child_effects() -> None:
    registry = build_runtime_service_registry(LocalModelChatStartup(),
        adapter_factory=lambda _config: pytest.fail("enabled adapter constructed"))
    descriptor = registry.descriptors[SERVICE_ID]
    assert descriptor.enabled is False
    assert descriptor.restart_policy == "never"
    assert tuple(registry.descriptors) == (SERVICE_ID,)


@pytest.mark.parametrize(
    ("config", "reason"),
    [
        (LocalModelChatStartup(enabled=True, serving_operation_id="serve-1"), "installation_identity_required"),
        (LocalModelChatStartup(enabled=True, installation_identity="install-1"), "serving_operation_id_required"),
        (LocalModelChatStartup(enabled=True, installation_identity="../bad", serving_operation_id="serve-1"), "invalid_installation_identity"),
        (LocalModelChatStartup(enabled=True, installation_identity="install-1", serving_operation_id="latest"), "serving_operation_id_invalid"),
    ],
)
def test_invalid_identity_fails_before_adapter_construction(config: LocalModelChatStartup, reason: str) -> None:
    with pytest.raises((ValueError, RuntimeError), match=reason):
        build_runtime_service_registry(config, adapter_factory=lambda _config: pytest.fail("adapter constructed"))


def test_service_surface_has_no_execution_or_model_injection_parameters() -> None:
    fields = set(LocalModelChatStartup.__dataclass_fields__)
    assert fields == {"enabled", "installation_identity", "serving_operation_id", "host", "port",
                      "resource_provisioning_id"}
    forbidden = {"executable", "script", "argv", "model_path", "activation_path", "runtime_path",
                 "interpreter_path", "custody_root", "preloaded_model", "simulation", "fallback"}
    assert not fields & forbidden
    assert set(inspect.signature(build_runtime_service_registry).parameters) == {
        "config", "adapter_factory", "installation_handle"}


def test_enabled_adapter_constructs_only_exact_launcher_argv() -> None:
    config = LocalModelChatStartup(enabled=True, installation_identity="Install-1",
                                   serving_operation_id="serve-explicit", port=5500)
    adapter = LocalModelChatServiceAdapter(config, probe=lambda _url: True)
    argv = adapter._argv
    assert Path(argv[1]).as_posix().endswith("/scripts/local_model_chat.py")
    assert argv[2:] == ("--installation-identity", "Install-1", "--serving-operation-id",
                        "serve-explicit", "--host", "127.0.0.1", "--port", "5500")
    assert "--model-path" not in argv and "--activation-path" not in argv
    assert "--simulation" not in argv and "--custody-root" not in argv
    assert set(adapter.identity) == {"adapter", "name"}


def test_resource_provisioning_selector_is_bounded_and_fixed_in_launcher() -> None:
    config = LocalModelChatStartup(enabled=True, installation_identity="install-1",
        serving_operation_id="serve-1", resource_provisioning_id="production.v1")
    adapter = LocalModelChatServiceAdapter(config, probe=lambda _url: True)
    assert adapter._argv[-2:] == ("--resource-provisioning-id", "production.v1")
    for invalid in ("", "../escape", "a/b", "a\\b", "all", "*"):
        with pytest.raises(ValueError, match="invalid_resource_provisioning_id"):
            LocalModelChatStartup(enabled=True, installation_identity="install-1",
                serving_operation_id="serve-1", resource_provisioning_id=invalid).validate()
    with pytest.raises(ValueError, match="resource_provisioning_requires_enabled_chat"):
        LocalModelChatStartup(resource_provisioning_id="production.v1").validate()


def test_legacy_bootstrap_paths_cannot_influence_production_composition() -> None:
    from sentientos.runtime.bootstrap import build_default_config

    legacy = build_default_config(Path("/legacy"))["runtime"]
    assert isinstance(legacy, dict) and {"model_path", "llama_server_path"} <= set(legacy)
    parameters = set(LocalModelChatStartup.__dataclass_fields__)
    assert not {"model_path", "llama_server_path"} & parameters


def test_semantic_health_distinguishes_current_unavailable_and_exit(monkeypatch) -> None:
    adapter = LocalModelChatServiceAdapter(LocalModelChatStartup(
        enabled=True, installation_identity="install-1", serving_operation_id="serve-1"),
        probe=lambda _url: True)
    monkeypatch.setattr("sentientos.runtime.services.ChildProcessServiceAdapter.health",
                        lambda _self: HealthResult(True, "process_alive"))
    assert adapter.health() == HealthResult(True, "serving_current")
    adapter._probe = lambda _url: False
    assert adapter.health() == HealthResult(False, "serving_unavailable")
    monkeypatch.setattr("sentientos.runtime.services.ChildProcessServiceAdapter.health",
                        lambda _self: HealthResult(False, "process_exited"))
    assert adapter.health() == HealthResult(False, "process_exited")


def test_readiness_is_coarse_and_does_not_establish_or_generate(monkeypatch) -> None:
    events: list[str] = []
    serving = SimpleNamespace(
        serving_is_current=lambda: events.append("inspect") or True,
        establish=lambda **_kwargs: events.append("establish"),
        close=lambda: events.append("close"),
        generate=lambda **_kwargs: events.append("generate"),
    )
    old = chat_service._PRODUCTION_COMPOSITION
    chat_service._PRODUCTION_COMPOSITION = chat_service.ProductionChatComposition(SimpleNamespace(), serving)
    try:
        assert asyncio.run(chat_service.readiness_endpoint()) == {"status": "ready"}
        assert events == ["inspect"]
    finally:
        chat_service._PRODUCTION_COMPOSITION = old


def test_readiness_unavailable_exposes_no_internal_identity(monkeypatch) -> None:
    monkeypatch.setattr(chat_service, "production_chat_ready", lambda: False)
    with pytest.raises(chat_service.HTTPException) as caught:
        asyncio.run(chat_service.readiness_endpoint())
    assert caught.value.status_code == 503
    assert caught.value.detail == "unavailable"


def test_local_chat_never_restarts_while_other_on_failure_service_does(tmp_path: Path) -> None:
    starts = {"chat": 0, "other": 0}
    registry = ServiceRegistry()
    for name, policy in (("chat", "never"), ("other", "on_failure")):
        adapter = InProcessServiceAdapter(name=name,
            start=lambda name=name: starts.__setitem__(name, starts[name] + 1),
            health=lambda: HealthResult(False, "failed"), stop=lambda: None)
        registry.register(RuntimeServiceDescriptor(service_id=name, display_name=name,
            service_kind="test", restart_policy=policy, min_backoff=0), adapter)
    supervisor = RuntimeSupervisor(registry, state_root=tmp_path, sleeper=lambda _delay: None)
    supervisor.start_all(); supervisor.observe()
    assert starts == {"chat": 1, "other": 2}


def test_runtime_loop_uses_one_supervisor_and_one_shutdown() -> None:
    events: list[str] = []
    class Supervisor:
        def __init__(self, registry, *, state_root=None):
            assert tuple(registry.descriptors) == (SERVICE_ID,); events.append("construct")
        def start_all(self): events.append("start")
        def observe(self): events.append("observe")
        def shutdown(self): events.append("shutdown")
    stopped = threading.Event(); stopped.set()
    assert run_canonical_runtime(LocalModelChatStartup(), stop_event=stopped,
                                 supervisor_factory=Supervisor) == 0
    assert events == ["construct", "start", "shutdown"]


def test_canonical_cli_passes_only_explicit_chat_configuration(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr("sentientos.runtime.startup.run_canonical_runtime",
                        lambda config, **kwargs: seen.append((config, kwargs)) or 0)
    assert ops.main(["runtime", "start", "--enable-local-model-chat",
                     "--installation-identity", "install-1",
                     "--serving-operation-id", "serve-1",
                     "--local-model-chat-port", "5501"]) == 0
    config, kwargs = seen[0]
    assert config == LocalModelChatStartup(enabled=True, installation_identity="install-1",
                                           serving_operation_id="serve-1", port=5501)
    assert kwargs == {"cadence_seconds": 2.0}


def test_canonical_cli_rejects_arbitrary_process_arguments() -> None:
    with pytest.raises(SystemExit):
        ops.main(["runtime", "start", "--enable-local-model-chat", "--argv", "evil"])


def test_actual_adapter_handoff_binds_live_child_and_source_generation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the real parent publisher and child verifier without serving a model."""
    import json
    import os
    import sys
    import time

    from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
    from sentientos.chat_process_generation import (
        ChatProcessGenerationError, RUNTIME_OBSERVATION_PATH,
        publish_chat_process_runtime_observation, read_stored_chat_process_runtime_observation,
        source_generation, verify_stored_chat_process_handoff,
    )
    from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceLedger
    from sentientos.host_resource_runtime import resource_consumption_world_state_records

    root = tmp_path / "runtime-source"
    (root / "sentientos").mkdir(parents=True)
    scripts = root / "scripts"
    scripts.mkdir()
    result_path = tmp_path / "child-result.json"
    release_path = tmp_path / "release-child"
    registry_root = tmp_path / "installation-state"
    helper = scripts / "local_model_chat.py"
    helper.write_text("""\
import json, os, sys, time
from pathlib import Path
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.chat_process_generation import verify_current_chat_process_handoff

args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
registry = InstallationStateRegistry._for_testing(Path(os.environ['TEST_REGISTRY_ROOT']))
handle = registry.open(InstallationIdentity.parse(args['--installation-identity']))
handoff = verify_current_chat_process_handoff(handle=handle, handoff_id=args['--runtime-handoff-id'])
if handoff['software_generation_digest'] != args['--expected-software-generation-digest']:
    raise SystemExit('source_generation_expectation_mismatch')
Path(os.environ['TEST_CHILD_RESULT']).write_text(json.dumps(handoff, sort_keys=True))
deadline = time.monotonic() + 10
while not Path(os.environ['TEST_RELEASE_CHILD']).exists() and time.monotonic() < deadline:
    time.sleep(.01)
""", encoding="utf-8")
    (root / "sentientos" / "marker.py").write_text("VALUE = 1\n", encoding="utf-8")

    identity = InstallationIdentity("handoff-test")
    handle = InstallationStateRegistry._for_testing(registry_root).open(identity, create=True)
    monkeypatch.setenv("TEST_REGISTRY_ROOT", str(registry_root))
    monkeypatch.setenv("TEST_CHILD_RESULT", str(result_path))
    monkeypatch.setenv("TEST_RELEASE_CHILD", str(release_path))
    real_root = Path(__file__).resolve().parents[1]

    def child_argv(config, *, root, runtime_handoff_id=None,
                   expected_source_generation_digest=None, **_kwargs):
        assert runtime_handoff_id is not None
        argv = (sys.executable, str(root / "scripts" / "local_model_chat.py"),
                "--installation-identity", config.installation_identity,
                "--serving-operation-id", config.serving_operation_id,
                "--runtime-handoff-id", runtime_handoff_id)
        if expected_source_generation_digest is not None:
            argv += ("--expected-software-generation-digest", expected_source_generation_digest)
        return argv

    monkeypatch.setattr(LocalModelChatServiceAdapter, "_launcher_argv", staticmethod(child_argv))
    config = LocalModelChatStartup(enabled=True, installation_identity=identity.value,
                                   serving_operation_id="serve-handoff")
    adapter = LocalModelChatServiceAdapter(config, installation_handle=handle)
    adapter._root = root
    adapter._launch_environment["PYTHONPATH"] = os.pathsep.join(
        (str(real_root), adapter._launch_environment["PYTHONPATH"]))
    adapter._environment = dict(adapter._launch_environment)
    try:
        adapter.start()
        parent_observation = adapter.current_runtime_handoff()
        stored_handoff = verify_stored_chat_process_handoff(handle=handle,
            handoff_id=parent_observation["handoff_id"],
            expected_digest=parent_observation["handoff_digest"])
        runtime_observation = publish_chat_process_runtime_observation(
            handle=handle, supervisor_generation="fixture-supervisor-generation",
            handoff=stored_handoff)
        assert runtime_observation["schema_version"] == "sentientos.chat_process_runtime_observation:v4"
        executable = runtime_observation["process_executable_observation"]
        assert executable["observation_status"] == "observed"
        assert executable["process_id"] == adapter._process.pid
        assert executable["parent_process_matches"] is True
        assert executable["executable_image_size_bytes"] > 0
        assert len(executable["executable_image_sha256"]) == 64
        assert executable["loaded_python_module_identity_posture"] == "not_independently_attested"
        assert read_stored_chat_process_runtime_observation(handle) == runtime_observation
        runtime_records = resource_consumption_world_state_records(
            ledger=GovernedLocalModelResourceLedger(tmp_path / "empty-resource-ledger.json"),
            source_identity={"installation_identity": identity.value},
            verified_chat_process_runtime_observation=runtime_observation)
        runtime_record = next(record for record in runtime_records
            if record.get("subject_kind") == "chat_process_runtime_generation_observation")
        assert runtime_record["payload"]["process_executable_observation"] == executable
        deadline = time.monotonic() + 5
        while not result_path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert result_path.exists(), (
            "child did not verify the published handoff: "
            + bytes(adapter._diagnostics).decode("utf-8", "replace"))
        child_observation = json.loads(result_path.read_text(encoding="utf-8"))
        assert child_observation["status"] == "runtime_launcher_process_and_source_bound"
        assert parent_observation["status"] == "runtime_launcher_child_launch_and_source_bound"
        for field in ("handoff_id", "handoff_digest", "process_instance_id",
                      "software_generation_digest", "process_id", "parent_process_id"):
            assert child_observation[field] == parent_observation[field]
        assert child_observation["process_id"] == adapter._process.pid
        assert child_observation["software_generation_digest"] == source_generation(root)[0]
        # Disk identity is independently reread; it is not loaded-module attestation.
        from sentientos.chat_process_generation import verify_stored_chat_process_handoff
        (root / "sentientos" / "marker.py").write_text("VALUE = 2\n", encoding="utf-8")
        assert adapter._process.poll() is None
        with pytest.raises(RuntimeError, match="chat_process_runtime_handoff_invalid"):
            adapter.current_runtime_handoff()
        historical = verify_stored_chat_process_handoff(handle=handle,
            handoff_id=child_observation["handoff_id"],
            expected_digest=child_observation["handoff_digest"])
        assert historical["software_generation_digest"] == child_observation["software_generation_digest"]
        assert historical["software_generation_digest"] != source_generation(root)[0]

        # Recomputed outer custody digests cannot legitimize contradictory
        # interpreter-parent evidence inside the v4 observation.
        forged = dict(runtime_observation)
        forged_executable = dict(executable)
        forged_executable["parent_process_matches"] = False
        from sentientos.chat_process_generation import _digest
        forged_executable["observation_digest"] = _digest({
            key: value for key, value in forged_executable.items()
            if key != "observation_digest"})
        forged["process_executable_observation"] = forged_executable
        from sentientos.local_runtime_provisioning import semantic_digest
        forged["observation_semantic_digest"] = semantic_digest({
            key: value for key, value in forged.items()
            if key != "observation_semantic_digest"})
        handle.durable_replace(handle.fixed_object(RUNTIME_OBSERVATION_PATH),
            (json.dumps(forged, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False) + "\n").encode("utf-8"))
        with pytest.raises(ChatProcessGenerationError,
                match="runtime_observation_process_executable_shape_invalid"):
            read_stored_chat_process_runtime_observation(handle)
    finally:
        release_path.write_text("release\n", encoding="utf-8")
        adapter.stop()
