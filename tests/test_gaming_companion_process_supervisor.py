from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_process_supervisor import (
    CompanionProcessLaunchSpec,
    GamingCompanionProcessSupervisor,
    validate_launch_spec,
)
from sentientos.gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
)

pytestmark = pytest.mark.no_legacy_skip


def _pair(number: int) -> BridgeGenerationPair:
    issued = (datetime.now(timezone.utc) + timedelta(seconds=number)).isoformat()
    source = BridgeGenerationCustodyRecord("windows-edge", f"edge-{number}",
        f"credential-store:edge-{number}", "operator-control-plane", issued,
        hex(number)[2:] * 64, f"edge-{number-1}" if number > 1 else None)
    acknowledgment = BridgeGenerationCustodyRecord("wsl-core", f"core-{number}",
        f"credential-store:core-{number}", "operator-control-plane", issued,
        hex(number + 4)[2:] * 64, f"core-{number-1}" if number > 1 else None)
    return BridgeGenerationPair(source, acknowledgment)


def _spec(tmp_path: Path) -> CompanionProcessLaunchSpec:
    return CompanionProcessLaunchSpec("wsl_core",
        (sys.executable, "-c", "import time; time.sleep(60)"), str(tmp_path),
        {"SENTIENTOS_COMPANION_ROLE": "wsl_core",
         "SENTIENTOS_COMPANION_MANIFEST": "/private/deployment.json"},
        startup_timeout_seconds=2, shutdown_timeout_seconds=1)


def test_supervisor_starts_recovers_with_rotated_generations_and_shuts_down(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    pairs = [_pair(1), _pair(2)]
    factory_calls: list[BridgeGenerationPair | None] = []

    def factory(previous):
        factory_calls.append(previous)
        return _spec(tmp_path), pairs[len(factory_calls) - 1]

    child_environments: list[dict[str, str]] = []

    def spawner(argv, **kwargs):
        child_environments.append(dict(kwargs["env"]))
        return __import__("subprocess").Popen(argv, **kwargs)

    supervisor = GamingCompanionProcessSupervisor(process_factory=factory,
        authority_receipt_verifier=lambda _digest, _record: True,
        launch_authorizer=lambda role, command_digest, generation:
            role == "wsl_core" and len(command_digest) == 64,
        health_probe=lambda child, _spec: child.poll() is None,
        max_restarts=1, poll_interval_seconds=0.02, spawner=spawner)
    started = supervisor.start()
    assert started.state == "running" and started.pid is not None
    assert "OPENAI_API_KEY" not in child_environments[0]
    assert factory_calls == [None]

    child = supervisor._child
    assert child is not None
    child.terminate()
    deadline = time.monotonic() + 4
    while supervisor.status().generation_id != "edge-2" and time.monotonic() < deadline:
        time.sleep(0.02)
    recovered = supervisor.status()
    assert recovered.state == "running"
    assert recovered.generation_id == "edge-2"
    assert recovered.restart_count == 1
    assert factory_calls == [None, pairs[0]]
    assert len(child_environments) == 2

    supervisor.close()
    assert supervisor.status().state == "stopped"


def test_launch_authority_denial_prevents_process_creation(tmp_path: Path) -> None:
    calls = 0

    def spawner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("denied process launch reached spawner")

    supervisor = GamingCompanionProcessSupervisor(
        process_factory=lambda _previous: (_spec(tmp_path), _pair(1)),
        authority_receipt_verifier=lambda _digest, _record: True,
        launch_authorizer=lambda _role, _command_digest, _generation: False,
        health_probe=lambda _child, _spec: True,
        spawner=spawner)
    with pytest.raises(CompanionBridgeError, match="launch_authority_denied"):
        supervisor.start()
    assert calls == 0
    assert supervisor.status().state == "failed"


def test_force_termination_requires_separate_explicit_authority(tmp_path: Path) -> None:
    class StubbornChild:
        pid = 2222
        kills = 0

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            self.kills += 1

        def wait(self, timeout=None):
            del timeout
            raise __import__("subprocess").TimeoutExpired("fixture", 1)

    supervisor = GamingCompanionProcessSupervisor(
        process_factory=lambda _previous: (_spec(tmp_path), _pair(1)),
        authority_receipt_verifier=lambda _digest, _record: True,
        launch_authorizer=lambda _role, _digest, _generation: True,
        health_probe=lambda _child, _spec: True)
    child = StubbornChild()
    with pytest.raises(CompanionBridgeError, match="forced_stop_authority_denied"):
        supervisor._stop_child(child, _spec(tmp_path))
    assert child.kills == 0


@pytest.mark.parametrize("environment", [
    {"OPENAI_API_KEY": "secret"},
    {"SENTIENTOS_COMPANION_ROLE": "wsl_core", "SENTIENTOS_COMPANION_TOKEN": "secret"},
])
def test_launch_spec_rejects_secret_environment_channels(tmp_path: Path, environment):
    candidate = CompanionProcessLaunchSpec("wsl_core", (sys.executable, "-m", "module"),
        str(tmp_path), environment)
    with pytest.raises(CompanionBridgeError, match="environment_invalid"):
        validate_launch_spec(candidate)
