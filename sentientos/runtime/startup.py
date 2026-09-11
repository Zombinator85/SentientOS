"""Canonical explicit runtime startup and deterministic shutdown loop."""
from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any, Callable

from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry

from .local_model_chat_service import (SERVICE_ID, LocalModelChatServiceAdapter,
                                       LocalModelChatStartup, build_runtime_service_registry)
from .local_model_chat_recovery import (ProductionLocalModelChatRecoveryController,
                                        build_startup_snapshot, write_startup_snapshot)
from .supervisor import RuntimeSupervisor


def run_canonical_runtime(
    config: LocalModelChatStartup,
    *,
    state_root: Path | None = None,
    cadence_seconds: float = 2.0,
    stop_event: threading.Event | None = None,
    supervisor_factory: Callable[..., RuntimeSupervisor] = RuntimeSupervisor,
) -> int:
    """Run one supervisor until an explicit termination signal/event.

    Registration and validation happen before supervisor or child construction.
    Observation never performs inference and this service's ``never`` policy prevents
    failed or stale serving from being re-established automatically.
    """
    if not 0.1 <= cadence_seconds <= 60.0:
        raise ValueError("runtime_cadence_out_of_range")
    registry = build_runtime_service_registry(config)
    supervisor = supervisor_factory(registry, state_root=state_root)
    stopping = stop_event or threading.Event()
    previous: dict[signal.Signals, Any] = {}

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
    try:
        supervisor.start_all()
        recovery = None
        if config.enabled:
            adapter = registry.adapter(SERVICE_ID)
            assert isinstance(adapter, LocalModelChatServiceAdapter)
            write_startup_snapshot(build_startup_snapshot(config, supervisor.generation), supervisor.root)
            assert config.installation_identity is not None
            handle = InstallationStateRegistry.system().open(
                InstallationIdentity.parse(config.installation_identity))
            recovery = ProductionLocalModelChatRecoveryController(
                supervisor, adapter, ControlPlaneKernel(), handle)
        while not stopping.wait(cadence_seconds):
            supervisor.observe()
            if recovery is not None:
                recovery.process_pending()
    finally:
        supervisor.shutdown()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return 0
