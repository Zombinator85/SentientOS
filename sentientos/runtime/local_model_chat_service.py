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
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sentientos.installation_state import InstallationIdentity
from sentientos.local_model_production_serving import _operation_id

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

    def validate(self) -> None:
        if self.host != "127.0.0.1":
            raise ValueError("local_model_chat_host_must_be_loopback")
        if not 1024 <= self.port <= 65535:
            raise ValueError("local_model_chat_port_out_of_range")
        if not self.enabled:
            return
        if self.installation_identity is None:
            raise ValueError("installation_identity_required")
        if self.serving_operation_id is None:
            raise ValueError("serving_operation_id_required")
        InstallationIdentity.parse(self.installation_identity)
        _operation_id(self.serving_operation_id)


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
                 probe: Callable[[str], bool] | None = None) -> None:
        config.validate()
        assert config.enabled and config.installation_identity and config.serving_operation_id
        root = Path(__file__).resolve().parents[2]
        argv = (sys.executable, str(root / "scripts" / "local_model_chat.py"),
                "--installation-identity", config.installation_identity,
                "--serving-operation-id", config.serving_operation_id,
                "--host", config.host, "--port", str(config.port))
        super().__init__(name=SERVICE_ID, argv=argv, cwd=root, environment=os.environ)
        self._readiness_url = f"http://{config.host}:{config.port}/readyz"
        self._probe = probe or _probe_readiness
        self._stopped = False

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
    *, adapter_factory: Callable[[LocalModelChatStartup], LocalModelChatServiceAdapter] = LocalModelChatServiceAdapter,
) -> ServiceRegistry:
    """Build the canonical registry without touching serving when chat is disabled."""
    config.validate()
    registry = ServiceRegistry()
    adapter = adapter_factory(config) if config.enabled else DisabledLocalModelChatAdapter()
    registry.register(RuntimeServiceDescriptor(
        service_id=SERVICE_ID, display_name="Hardened local-model chat",
        service_kind="hardened_local_model_chat", enabled=config.enabled,
        health_posture="semantic", restart_policy="never", restart_budget=0,
    ), adapter)
    return registry
