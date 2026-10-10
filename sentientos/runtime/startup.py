"""Canonical explicit runtime startup and deterministic shutdown loop."""
from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.installation_state import InstallationIdentity, InstallationStateError, InstallationStateRegistry
from sentientos.chat_process_generation import (
    ChatProcessGenerationError, publish_chat_process_runtime_observation,
    read_stored_chat_process_runtime_observation, verify_stored_chat_process_handoff,
)

from .local_model_chat_service import (SERVICE_ID, LocalModelChatServiceAdapter,
                                       LocalModelChatStartup, build_runtime_service_registry)
from .local_model_chat_recovery import (ProductionLocalModelChatRecoveryController,
                                        LocalModelChatRecoveryError, build_startup_snapshot,
                                        read_startup_snapshot, write_startup_snapshot)
from .supervisor import RuntimeSupervisor


def run_canonical_runtime(
    config: LocalModelChatStartup,
    *,
    state_root: Path | None = None,
    cadence_seconds: float = 2.0,
    stop_event: threading.Event | None = None,
    supervisor_factory: Callable[..., RuntimeSupervisor] = RuntimeSupervisor,
) -> int:
    """Run one installation owner until explicit termination.

    An installation-scoped lock prevents overlapping supervisors from
    publishing competing current-process observations. The lock grants no
    model, inference, memory, host, or external-effect authority.
    """
    if not 0.1 <= cadence_seconds <= 60.0:
        raise ValueError("runtime_cadence_out_of_range")
    handle = None
    if config.enabled:
        assert config.installation_identity is not None
        handle = InstallationStateRegistry.system().open(
            InstallationIdentity.parse(config.installation_identity))
    owner_lock = None
    if handle is not None:
        lock_dir = handle.fixed_object("local-model/chat/runtime-locks")
        handle.ensure_directory(lock_dir)
        owner_lock = handle.exclusive_lock(
            handle.fixed_object("local-model/chat/runtime-locks/supervisor.lock"), blocking=False)
        try:
            owner_lock.__enter__()
        except InstallationStateError as exc:
            raise RuntimeError("chat_runtime_installation_owner_already_held") from exc
    try:
        return _run_canonical_runtime_owned(config, handle, state_root=state_root,
            cadence_seconds=cadence_seconds, stop_event=stop_event,
            supervisor_factory=supervisor_factory)
    finally:
        if owner_lock is not None:
            owner_lock.__exit__(None, None, None)


def _run_canonical_runtime_owned(
    config: LocalModelChatStartup,
    handle: Any,
    *,
    state_root: Path | None,
    cadence_seconds: float,
    stop_event: threading.Event | None,
    supervisor_factory: Callable[..., RuntimeSupervisor],
) -> int:
    registry = build_runtime_service_registry(config, installation_handle=handle)
    supervisor = supervisor_factory(registry, state_root=state_root)
    if handle is not None:
        try:
            previous_runtime_observation = read_stored_chat_process_runtime_observation(handle)
        except ChatProcessGenerationError:
            previous_runtime_observation = None
        if (isinstance(previous_runtime_observation, Mapping)
                and previous_runtime_observation.get("runtime_status") == "running_observed"):
            try:
                predecessor_handoff = verify_stored_chat_process_handoff(
                    handle=handle,
                    handoff_id=str(previous_runtime_observation.get("handoff_id", "")),
                    expected_digest=str(previous_runtime_observation.get("handoff_digest", "")))
                publish_chat_process_runtime_observation(
                    handle=handle, supervisor_generation=supervisor.generation,
                    handoff=predecessor_handoff, status="not_verified",
                    reason_code="new_supervisor_has_not_verified_child")
            except ChatProcessGenerationError:
                # Invalid old custody remains visible as invalid to the
                # read-only observer; startup does not repair or rewrite it.
                pass
    previous_snapshot: dict[str, Any] | None = None
    if config.enabled:
        try:
            previous_snapshot = read_startup_snapshot(supervisor.root)
        except LocalModelChatRecoveryError as exc:
            if exc.code != "runtime_startup_snapshot_unavailable":
                raise
    if config.enabled and previous_snapshot is not None:
        adapter = registry.adapter(SERVICE_ID)
        assert isinstance(adapter, LocalModelChatServiceAdapter)
        adapter.bind_prior_startup_snapshot(previous_snapshot)
    stopping = stop_event or threading.Event()
    previous: dict[signal.Signals, Any] = {}

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
    last_handoff: Mapping[str, Any] | None = None
    try:
        supervisor.start_all()
        recovery = None
        adapter = None
        if config.enabled:
            adapter = registry.adapter(SERVICE_ID)
            assert isinstance(adapter, LocalModelChatServiceAdapter)
            handoff = adapter.current_runtime_handoff()
            if not isinstance(handoff, Mapping):
                raise RuntimeError("chat_process_runtime_handoff_unavailable")
            last_handoff = dict(handoff)
            write_startup_snapshot(build_startup_snapshot(
                config, supervisor.generation, runtime_handoff=handoff), supervisor.root)
            assert handle is not None
            try:
                publish_chat_process_runtime_observation(handle=handle,
                    supervisor_generation=supervisor.generation, handoff=handoff,
                    status="running_observed")
            except ChatProcessGenerationError:
                # The supervised chat runtime remains governed by its own
                # lifecycle. A failed optional observation is not converted
                # into a fabricated successful record.
                pass
            recovery = ProductionLocalModelChatRecoveryController(
                supervisor, adapter, ControlPlaneKernel(), handle)
        while not stopping.wait(cadence_seconds):
            supervisor.observe()
            if recovery is not None and adapter is not None and handle is not None:
                try:
                    observed_handoff = adapter.current_runtime_handoff()
                except Exception:
                    if last_handoff is not None:
                        try:
                            publish_chat_process_runtime_observation(
                                handle=handle, supervisor_generation=supervisor.generation,
                                handoff=last_handoff, status="not_verified",
                                reason_code="current_handoff_unavailable")
                        except ChatProcessGenerationError:
                            pass
                else:
                    if isinstance(observed_handoff, Mapping):
                        last_handoff = dict(observed_handoff)
                        try:
                            publish_chat_process_runtime_observation(
                                handle=handle, supervisor_generation=supervisor.generation,
                                handoff=observed_handoff, status="running_observed")
                        except ChatProcessGenerationError:
                            pass
                recovery.process_pending()
    finally:
        supervisor.shutdown()
        if handle is not None and last_handoff is not None:
            try:
                publish_chat_process_runtime_observation(
                    handle=handle, supervisor_generation=supervisor.generation,
                    handoff=last_handoff, status="not_verified",
                    reason_code="supervisor_shutdown")
            except ChatProcessGenerationError:
                pass
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return 0
