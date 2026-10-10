"""Exact supervised composition for hardened production local-model chat.

This surface deliberately accepts no paths, executable, argv, custody override,
preloaded object, or simulation posture.  Legacy bootstrap model/runtime fields are
not authoritative inputs and are never inspected here.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sentientos.installation_state import InstallationIdentity, InstallationStateHandle
from sentientos.local_model_production_serving import _operation_id
from sentientos.local_model_production_serving import _semantic_digest
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.chat_process_generation import publish_chat_process_handoff

from .services import ChildProcessServiceAdapter, HealthResult
from .supervisor import RuntimeServiceDescriptor, ServiceRegistry

SERVICE_ID = "local_model_chat"


@dataclass(frozen=True)
class LocalModelChatStartup:
    enabled: bool = False
    installation_identity: str | None = None
    serving_operation_id: str | None = None
    host: str = "127.0.0.1"
    port: int = 5000
    resource_provisioning_id: str | None = None

    def validate(self) -> None:
        if self.host != "127.0.0.1":
            raise ValueError("local_model_chat_host_must_be_loopback")
        if not 1024 <= self.port <= 65535:
            raise ValueError("local_model_chat_port_out_of_range")
        if not self.enabled:
            if self.resource_provisioning_id is not None:
                raise ValueError("resource_provisioning_requires_enabled_chat")
            return
        if self.installation_identity is None:
            raise ValueError("installation_identity_required")
        if self.serving_operation_id is None:
            raise ValueError("serving_operation_id_required")
        InstallationIdentity.parse(self.installation_identity)
        _operation_id(self.serving_operation_id)
        if self.resource_provisioning_id is not None:
            from sentientos.production_chat_resource_provisioning import validate_resource_provisioning_id
            validate_resource_provisioning_id(self.resource_provisioning_id)


class DisabledLocalModelChatAdapter:
    @property
    def identity(self) -> dict[str, str]: return {"adapter": "disabled", "name": SERVICE_ID}
    def start(self) -> None: raise RuntimeError("disabled_service_cannot_start")
    def health(self) -> HealthResult: return HealthResult(False, "disabled")
    def stop(self) -> None: return None
    def force_stop(self) -> None: return None


class LocalModelChatServiceAdapter(ChildProcessServiceAdapter):
    """Fixed-launcher child custody plus loopback semantic readiness."""

    def __init__(self, config: LocalModelChatStartup, *,
                 probe: Callable[[str], bool] | None = None,
                 installation_handle: InstallationStateHandle | None = None) -> None:
        config.validate()
        assert config.enabled and config.installation_identity and config.serving_operation_id
        root = Path(__file__).resolve().parents[2]
        if (installation_handle is not None
                and installation_handle.identity.value != InstallationIdentity.parse(config.installation_identity).value):
            raise ValueError("chat_process_handoff_installation_mismatch")
        if installation_handle is not None and os.name != "posix":
            raise ValueError("chat_process_handoff_publication_unsupported_platform")
        self._config = config
        self._root = root
        self._installation_handle = installation_handle
        self._handoff_id = uuid.uuid4().hex if installation_handle is not None else None
        environment = dict(os.environ)
        for key in ("PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONUSERBASE"):
            environment.pop(key, None)
        environment["PYTHONPATH"] = str(root)
        environment["PYTHONNOUSERSITE"] = "1"
        self._launch_environment = environment
        argv = self._launcher_argv(config, root=root, runtime_handoff_id=self._handoff_id)
        super().__init__(name=SERVICE_ID, argv=argv, cwd=root, environment=environment)
        self._readiness_url = f"http://{config.host}:{config.port}/readyz"
        self._probe = probe or _probe_readiness
        self._stopped = False

    @staticmethod
    def _launcher_argv(config: LocalModelChatStartup, *, root: Path,
                       expected_activation_state_digest: str | None = None,
                       runtime_handoff_id: str | None = None) -> tuple[str, ...]:
        assert config.installation_identity is not None and config.serving_operation_id is not None
        argv: tuple[str, ...] = (sys.executable, str(root / "scripts" / "local_model_chat.py"),
                "--installation-identity", config.installation_identity,
                "--serving-operation-id", config.serving_operation_id,
                "--host", config.host, "--port", str(config.port))
        if expected_activation_state_digest is not None:
            argv += ("--expected-activation-state-digest", expected_activation_state_digest)
        if runtime_handoff_id is not None:
            argv += ("--runtime-handoff-id", runtime_handoff_id)
        if config.resource_provisioning_id is not None:
            argv += ("--resource-provisioning-id", config.resource_provisioning_id)
        return argv

    def _restart_with_fresh_serving_operation(
        self, *, replacement_serving_operation_id: str,
        expected_activation_state_digest: str,
    ) -> None:
        """Replace exactly this child's lifetime; never retries or changes custody."""
        replacement = _operation_id(replacement_serving_operation_id)
        expected = _semantic_digest(expected_activation_state_digest)
        self.stop()
        if self._process is not None and self._process.poll() is None:
            self.force_stop()
        self._config = LocalModelChatStartup(True, self._config.installation_identity,
                                             replacement, self._config.host, self._config.port,
                                             self._config.resource_provisioning_id)
        self._handoff_id = uuid.uuid4().hex if self._installation_handle is not None else None
        self._argv = self._launcher_argv(self._config, root=self._root,
            expected_activation_state_digest=expected, runtime_handoff_id=self._handoff_id)
        self._stopped = False
        self.start()

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        super().start()
        if self._installation_handle is None or self._handoff_id is None:
            return
        process = self._process
        if process is None or process.poll() is not None:
            raise RuntimeError("chat_process_exited_before_handoff_publication")
        startup_timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        try:
            publish_chat_process_handoff(handle=self._installation_handle,
                handoff_id=self._handoff_id, argv=self._argv, environment=self._launch_environment,
                working_directory=self._cwd, process_id=process.pid, parent_process_id=os.getpid(),
                startup_timestamp=startup_timestamp, python_executable=self._argv[0],
                repository_root=self._root)
        except Exception:
            self.force_stop()
            raise

    @property
    def startup_configuration(self) -> LocalModelChatStartup:
        return self._config

    @property
    def identity(self) -> dict[str, str]:
        return {"adapter": "hardened_local_model_chat", "name": SERVICE_ID}

    def health(self) -> HealthResult:
        process_health = super().health()
        if not process_health.ready:
            return HealthResult(False, "process_exited")
        ready = self._probe(self._readiness_url)
        return HealthResult(ready, "serving_current" if ready else "serving_unavailable")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        super().stop()
        process = self._process
        if process is not None:
            try: process.wait(timeout=5.0)
            except subprocess.TimeoutExpired: self.force_stop()

    def force_stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            super().force_stop()


def _probe_readiness(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            payload = json.loads(response.read(256))
            return bool(response.status == 200 and payload == {"status": "ready"})
    except (OSError, ValueError, urllib.error.URLError):
        return False


def build_runtime_service_registry(
    config: LocalModelChatStartup,
    *, adapter_factory: Callable[..., LocalModelChatServiceAdapter] = LocalModelChatServiceAdapter,
    installation_handle: InstallationStateHandle | None = None,
) -> ServiceRegistry:
    """Build the canonical registry without touching serving when chat is disabled."""
    config.validate()
    registry = ServiceRegistry()
    if config.enabled:
        adapter = (adapter_factory(config, installation_handle=installation_handle)
                   if installation_handle is not None else adapter_factory(config))
    else:
        adapter = DisabledLocalModelChatAdapter()
    registry.register(RuntimeServiceDescriptor(
        service_id=SERVICE_ID, display_name="Hardened local-model chat",
        service_kind="hardened_local_model_chat", enabled=config.enabled,
        health_posture="semantic", restart_policy="never", restart_budget=0,
    ), adapter)
    return registry
