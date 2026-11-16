from __future__ import annotations

from datetime import datetime, timezone
import threading

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_edge_supervisor_entrypoint import (
    run_windows_edge_supervisor,
)
from sentientos.gaming_companion_process_supervisor import (
    CompanionProcessLaunchSpec,
    GamingCompanionProcessSupervisor,
)
from sentientos.gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
)
from tests.test_gaming_companion_role_entrypoint import _manifest

pytestmark = pytest.mark.no_legacy_skip


class _Child:
    pid = 711

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.running = True

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.events.append("edge_stopped")
        self.running = False

    def kill(self):
        self.running = False

    def wait(self, timeout=None):
        del timeout
        self.running = False
        return 0


def _generation_pair() -> BridgeGenerationPair:
    issued = datetime.now(timezone.utc).isoformat()
    return BridgeGenerationPair(
        BridgeGenerationCustodyRecord("windows-edge", "edge-generation-1",
            "credential-store:edge-generation-1", "fixture-authority", issued,
            "a" * 64, None),
        BridgeGenerationCustodyRecord("wsl-core", "core-generation-1",
            "credential-store:core-generation-1", "fixture-authority", issued,
            "b" * 64, None))


def _supervisor(tmp_path, role: str, events: list[str], spawns: list[str]):
    spec = CompanionProcessLaunchSpec(role,
        ("python", "-m", "sentientos.gaming_companion_role_entrypoint",
         "--role", role, "--manifest", str(tmp_path / "deployment.json")),
        str(tmp_path), {"SENTIENTOS_COMPANION_ROLE": role})

    def spawn(argv, **kwargs):
        del kwargs
        spawns.append(argv[argv.index("--role") + 1])
        return _Child(events)

    return GamingCompanionProcessSupervisor(
        process_factory=lambda _previous: (spec, _generation_pair()),
        authority_receipt_verifier=lambda _digest, _record: True,
        launch_authorizer=lambda selected_role, _digest, _generation:
            selected_role == role,
        health_probe=lambda child, _spec: child.poll() is None,
        expected_role=role, poll_interval_seconds=0.01, spawner=spawn)


def test_edge_supervisor_authorizes_then_owns_only_windows_edge(tmp_path) -> None:
    events: list[str] = []
    spawns: list[str] = []
    calls: list[str] = []
    supervisor = _supervisor(tmp_path, "windows_edge", events, spawns)
    stop = threading.Event()
    stop.set()

    result = run_windows_edge_supervisor(
        manifest=_manifest(),
        supervisor_provider=lambda _manifest: calls.append("provider") or supervisor,
        launch_authorizer=lambda _manifest: calls.append("authorize") or True,
        stop_event=stop, poll_interval_seconds=0.05, system_name="Windows")

    assert result == 0
    assert calls == ["authorize", "provider"]
    assert spawns == ["windows_edge"]
    assert events == ["edge_stopped"]
    assert supervisor.status().state == "stopped"


def test_edge_supervisor_rejects_core_owner_before_any_process_start(tmp_path) -> None:
    events: list[str] = []
    spawns: list[str] = []
    supervisor = _supervisor(tmp_path, "wsl_core", events, spawns)

    with pytest.raises(CompanionBridgeError,
                       match="companion_edge_supervisor_role_mismatch"):
        run_windows_edge_supervisor(manifest=_manifest(),
            supervisor_provider=lambda _manifest: supervisor,
            launch_authorizer=lambda _manifest: True,
            stop_event=threading.Event(), system_name="Windows")

    assert spawns == []
    assert events == []


def test_edge_supervisor_deployment_denial_precedes_provider(tmp_path) -> None:
    events: list[str] = []
    calls: list[str] = []
    supervisor = _supervisor(tmp_path, "windows_edge", events, [])

    with pytest.raises(CompanionBridgeError,
                       match="companion_pair_launch_authority_denied"):
        run_windows_edge_supervisor(manifest=_manifest(),
            supervisor_provider=lambda _manifest: calls.append("provider") or supervisor,
            launch_authorizer=lambda _manifest: calls.append("authorize") and False,
            stop_event=threading.Event(), system_name="Windows")

    assert calls == ["authorize"]
    assert events == []
