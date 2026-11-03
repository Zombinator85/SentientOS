from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import time

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_pair_supervisor import GamingCompanionPairSupervisor
from sentientos.gaming_companion_process_supervisor import (
    CompanionProcessLaunchSpec,
    GamingCompanionProcessSupervisor,
)
from sentientos.gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
)

pytestmark = pytest.mark.no_legacy_skip


class _Child:
    _next_pid = 10_000

    def __init__(self, role: str, events: list[str]) -> None:
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.role = role
        self.events = events
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.events.append("terminate:" + self.role)
        self.returncode = 0

    def kill(self) -> None:
        self.events.append("kill:" + self.role)
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.role, 1)
        return self.returncode


def _generation_pair(role: str, number: int = 1) -> BridgeGenerationPair:
    issued = (datetime.now(timezone.utc) + timedelta(seconds=number)).isoformat()
    source = BridgeGenerationCustodyRecord(role + "-source", role + "-source-" + str(number),
        "credential-store:" + role + ":source", "operator-control-plane", issued,
        ("a" if role == "wsl_core" else "c") * 64,
        role + "-source-" + str(number - 1) if number > 1 else None)
    acknowledgment = BridgeGenerationCustodyRecord(role + "-ack", role + "-ack-" + str(number),
        "credential-store:" + role + ":ack", "operator-control-plane", issued,
        ("b" if role == "wsl_core" else "d") * 64,
        role + "-ack-" + str(number - 1) if number > 1 else None)
    return BridgeGenerationPair(source, acknowledgment)


def _owner(role: str, tmp_path: Path, events: list[str], *, allow: bool = True,
           launch_role: str | None = None) -> GamingCompanionProcessSupervisor:
    pair = _generation_pair(role)

    def factory(_previous):
        events.append("authorize-records:" + role)
        spec = CompanionProcessLaunchSpec(
            launch_role or role, (sys.executable, "-c", "pass"), str(tmp_path),
            {"SENTIENTOS_COMPANION_ROLE": launch_role or role,
             "SENTIENTOS_COMPANION_MANIFEST": str(tmp_path / "deployment.json")},
            startup_timeout_seconds=1, shutdown_timeout_seconds=1)
        return spec, pair

    def spawn(argv, **kwargs):
        del argv, kwargs
        events.append("spawn:" + role)
        return _Child(role, events)

    return GamingCompanionProcessSupervisor(
        process_factory=factory,
        authority_receipt_verifier=lambda _digest, _record: True,
        launch_authorizer=lambda selected_role, _digest, _generation:
            events.append("launch:" + role) or (allow and selected_role == (launch_role or role)),
        health_probe=lambda child, _spec: child.poll() is None,
        poll_interval_seconds=0.02, spawner=spawn)


def _deployment(tmp_path: Path, events: list[str], *, edge_allow: bool = True,
                edge_launch_role: str | None = None) -> tuple[GamingCompanionPairSupervisor,
                                                              GamingCompanionProcessSupervisor,
                                                              GamingCompanionProcessSupervisor]:
    core = _owner("wsl_core", tmp_path, events)
    edge = _owner("windows_edge", tmp_path, events, allow=edge_allow,
                  launch_role=edge_launch_role)
    return GamingCompanionPairSupervisor(core=core, edge=edge,
        poll_interval_seconds=0.05), core, edge


def test_pair_starts_core_then_edge_and_shuts_down_edge_then_core(tmp_path: Path) -> None:
    events: list[str] = []
    pair, core, edge = _deployment(tmp_path, events)

    status = pair.start()
    assert status.state == "running"
    assert status.core.role == "wsl_core" and status.edge.role == "windows_edge"
    assert events.index("spawn:wsl_core") < events.index("spawn:windows_edge")

    pair.close()
    assert events.index("terminate:windows_edge") < events.index("terminate:wsl_core")
    assert pair.status().state == "stopped"
    assert core.status().state == "stopped" and edge.status().state == "stopped"


def test_edge_start_denial_rolls_back_already_started_core(tmp_path: Path) -> None:
    events: list[str] = []
    pair, core, edge = _deployment(tmp_path, events, edge_allow=False)

    with pytest.raises(CompanionBridgeError, match="launch_authority_denied"):
        pair.start()

    assert "spawn:wsl_core" in events
    assert "spawn:windows_edge" not in events
    assert "terminate:wsl_core" in events
    assert core.status().state == "stopped"
    assert edge.status().state == "stopped"
    assert pair.status().state == "failed"


def test_role_identity_mismatch_rolls_back_and_pair_cannot_restart(tmp_path: Path) -> None:
    events: list[str] = []
    pair, core, _edge = _deployment(tmp_path, events, edge_launch_role="wsl_core")

    with pytest.raises(CompanionBridgeError, match="companion_pair_role_not_running:windows_edge"):
        pair.start()

    assert "terminate:windows_edge" in events
    assert "terminate:wsl_core" in events
    with pytest.raises(CompanionBridgeError, match="supervisor_already_started"):
        pair.start()
    assert core.status().state == "stopped"


def test_role_exhausting_recovery_stops_its_peer(tmp_path: Path) -> None:
    events: list[str] = []
    pair, core, edge = _deployment(tmp_path, events)
    pair.start()
    core.close()

    deadline = time.monotonic() + 2
    while pair.status().state != "failed" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert pair.status().state == "failed"
    assert edge.status().state == "stopped"
    assert "terminate:windows_edge" in events
    pair.close()


def test_pair_close_attempts_both_owners_when_one_close_fails(tmp_path: Path) -> None:
    events: list[str] = []
    pair, _core, edge = _deployment(tmp_path, events)
    pair.start()
    original_close = edge.close

    def failing_close() -> None:
        original_close()
        raise RuntimeError("private detail must not be reported")

    edge.close = failing_close  # type: ignore[method-assign]
    with pytest.raises(CompanionBridgeError, match="RuntimeError"):
        pair.close()
    assert "terminate:windows_edge" in events
    assert "terminate:wsl_core" in events
    assert pair.status().state == "failed"
