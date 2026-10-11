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
from typing import Callable, Mapping

from sentientos.installation_state import InstallationIdentity, InstallationStateHandle
from sentientos.local_model_production_serving import _operation_id
from sentientos.local_model_production_serving import _semantic_digest
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.chat_process_generation import (
    publish_chat_process_handoff, publish_chat_process_runtime_observation,
    source_generation, verify_stored_chat_process_handoff,
    verify_supervised_chat_process_handoff,
)

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
        self._published_handoff_record: dict[str, object] | None = None
        self._runtime_supervisor_generation: str | None = None
        self._prior_startup_snapshot: dict[str, object] | None = None
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

    def bind_prior_startup_snapshot(self, snapshot: Mapping[str, object]) -> None:
        if self._installation_handle is None:
            raise ValueError("chat_process_handoff_installation_handle_required")
        if snapshot.get("installation_identity") != self._installation_handle.identity.value:
            raise ValueError("chat_process_predecessor_installation_mismatch")
        snapshot_digest = snapshot.get("snapshot_semantic_digest")
        supervisor_generation = snapshot.get("runtime_supervisor_generation")
        if (not isinstance(snapshot_digest, str) or len(snapshot_digest) != 64
                or any(character not in "0123456789abcdef" for character in snapshot_digest)
                or not isinstance(supervisor_generation, str) or not supervisor_generation):
            raise ValueError("chat_process_predecessor_snapshot_invalid")
        self._prior_startup_snapshot = None
        predecessor = snapshot.get("chat_process_handoff")
        if predecessor is not None and not isinstance(predecessor, Mapping):
            raise ValueError("chat_process_predecessor_handoff_malformed")
        if isinstance(predecessor, Mapping):
            historical = verify_stored_chat_process_handoff(
                handle=self._installation_handle,
                handoff_id=str(predecessor.get("handoff_id", "")),
                expected_digest=str(predecessor.get("handoff_digest", "")))
            for key in ("handoff_id", "handoff_digest", "process_instance_id",
                    "software_generation_digest", "process_id", "parent_process_id",
                    "startup_timestamp", "source_generation_scope"):
                if predecessor.get(key) != historical.get(key):
                    raise ValueError("chat_process_predecessor_handoff_mismatch")
            self._prior_startup_snapshot = dict(snapshot)

    @staticmethod
    def _launcher_argv(config: LocalModelChatStartup, *, root: Path,
                       expected_activation_state_digest: str | None = None,
                       runtime_handoff_id: str | None = None,
                       expected_source_generation_digest: str | None = None) -> tuple[str, ...]:
        assert config.installation_identity is not None and config.serving_operation_id is not None
        argv: tuple[str, ...] = (sys.executable, str(root / "scripts" / "local_model_chat.py"),
                "--installation-identity", config.installation_identity,
                "--serving-operation-id", config.serving_operation_id,
                "--host", config.host, "--port", str(config.port))
        if expected_activation_state_digest is not None:
            argv += ("--expected-activation-state-digest", expected_activation_state_digest)
        if runtime_handoff_id is not None:
            argv += ("--runtime-handoff-id", runtime_handoff_id)
        if expected_source_generation_digest is not None:
            argv += ("--expected-software-generation-digest", expected_source_generation_digest)
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
        self._published_handoff_record = None
        self._argv = self._launcher_argv(self._config, root=self._root,
            expected_activation_state_digest=expected, runtime_handoff_id=self._handoff_id)
        self._stopped = False
        self.start()

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        source_snapshot = None
        if self._installation_handle is not None and self._handoff_id is not None:
            source_snapshot = source_generation(self._root)
            self._argv = self._launcher_argv(self._config, root=self._root,
                runtime_handoff_id=self._handoff_id,
                expected_source_generation_digest=source_snapshot[0])
        super().start()
        if self._installation_handle is None or self._handoff_id is None:
            return
        process = self._process
        if process is None or process.poll() is not None:
            raise RuntimeError("chat_process_exited_before_handoff_publication")
        startup_timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        try:
            self._published_handoff_record = publish_chat_process_handoff(
                handle=self._installation_handle, handoff_id=self._handoff_id,
                argv=self._argv, environment=self._launch_environment,
                working_directory=self._cwd, process_id=process.pid,
                parent_process_id=os.getpid(), startup_timestamp=startup_timestamp,
                python_executable=self._argv[0], repository_root=self._root,
                prior_startup_snapshot=self._prior_startup_snapshot,
                source_snapshot=source_snapshot)
        except Exception:
            self.force_stop()
            raise

    def current_runtime_handoff(self) -> dict[str, object] | None:
        if self._installation_handle is None or self._handoff_id is None:
            return None
        process = self._process
        if process is None or process.poll() is not None:
            raise RuntimeError("chat_process_runtime_handoff_child_not_running")
        try:
            return verify_supervised_chat_process_handoff(
                handle=self._installation_handle, handoff_id=self._handoff_id,
                process_id=process.pid, parent_process_id=os.getpid(), argv=self._argv,
                environment=self._launch_environment, working_directory=self._cwd,
                python_executable=self._argv[0], repository_root=self._root)
        except Exception as exc:
            raise RuntimeError("chat_process_runtime_handoff_invalid") from exc

    def bind_runtime_supervisor_generation(self, generation: str) -> None:
        if not isinstance(generation, str) or not generation or len(generation) > 128:
            raise ValueError("chat_runtime_supervisor_generation_invalid")
        self._runtime_supervisor_generation = generation

    def _publish_runtime_observation(self, *, running: bool,
                                     reason_code: str | None = None) -> bool:
        if self._installation_handle is None or self._handoff_id is None:
            return True
        generation = self._runtime_supervisor_generation
        record = self._published_handoff_record
        if (not isinstance(generation, str) or not generation
                or not isinstance(record, Mapping)
                or not isinstance(record.get("handoff_digest"), str)):
            return False
        try:
            historical = verify_stored_chat_process_handoff(
                handle=self._installation_handle, handoff_id=self._handoff_id,
                expected_digest=str(record["handoff_digest"]))
            if running:
                supervised = self.current_runtime_handoff()
                if (supervised.get("handoff_id") != historical.get("handoff_id")
                        or supervised.get("handoff_digest") != historical.get("handoff_digest")
                        or supervised.get("process_instance_id") != historical.get("process_instance_id")
                        or supervised.get("process_id") != historical.get("process_id")):
                    return False
                publish_chat_process_runtime_observation(
                    handle=self._installation_handle,
                    supervisor_generation=generation,
                    handoff=historical, status="running_observed")
            else:
                if reason_code is None:
                    return False
                publish_chat_process_runtime_observation(
                    handle=self._installation_handle,
                    supervisor_generation=generation,
                    handoff=historical, status="not_verified",
                    reason_code=reason_code,
                    configured_serving_receipt_posture="runtime_not_verified")
            return True
        except Exception:
            return False

    @property
    def startup_configuration(self) -> LocalModelChatStartup:
        return self._config

    @property
    def identity(self) -> dict[str, str]:
        return {"adapter": "hardened_local_model_chat", "name": SERVICE_ID}

    def health(self) -> HealthResult:
        process_health = super().health()
        if not process_health.ready:
            self._publish_runtime_observation(
                running=False, reason_code="child_not_running")
            return HealthResult(False, "process_exited")
        ready = self._probe(self._readiness_url)
        if not ready:
            if not self._publish_runtime_observation(
                    running=False, reason_code="readiness_unavailable"):
                return HealthResult(False, "runtime_observation_unavailable")
            return HealthResult(False, "serving_unavailable")
        if not self._publish_runtime_observation(running=True):
            return HealthResult(False, "runtime_observation_unavailable")
        return HealthResult(True, "serving_current")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        super().stop()
        process = self._process
        if process is not None:
            try: process.wait(timeout=5.0)
            except subprocess.TimeoutExpired: self.force_stop()
        if process is None or process.poll() is not None:
            self._publish_runtime_observation(
                running=False, reason_code="child_exit_observed")

    def force_stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            super().force_stop()
        if self._process is not None and self._process.poll() is not None:
            self._publish_runtime_observation(
                running=False, reason_code="child_exit_observed")


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
