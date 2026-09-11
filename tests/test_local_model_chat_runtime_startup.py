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
    assert fields == {"enabled", "installation_identity", "serving_operation_id", "host", "port"}
    forbidden = {"executable", "script", "argv", "model_path", "activation_path", "runtime_path",
                 "interpreter_path", "custody_root", "preloaded_model", "simulation", "fallback"}
    assert not fields & forbidden
    assert set(inspect.signature(build_runtime_service_registry).parameters) == {"config", "adapter_factory"}


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
