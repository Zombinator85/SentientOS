from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.gaming_companion_authority import CompanionAuthorityCallbacks
from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_pair_supervisor import GamingCompanionPairSupervisor
from sentientos.gaming_companion_platform_installation import CompanionPlatformInstallation
from sentientos.gaming_companion_platform_pair_process import (
    GamingCompanionPlatformPairProcessProvider,
)
from sentientos.gaming_companion_process_supervisor import CompanionProcessLaunchSpec
from sentientos.gaming_companion_tls_transport import BridgeGenerationCustodyRecord, BridgeGenerationPair
from tests.test_gaming_companion_deployment import _reverse_mutual_tls_manifest

pytestmark = pytest.mark.no_legacy_skip


class _Child:
    def __init__(self, pid: int, events: list[str]) -> None:
        self.pid = pid
        self._events = events
        self._running = True

    def poll(self) -> int | None:
        return None if self._running else 0

    def terminate(self) -> None:
        self._events.append(f"stop:{self.pid}")
        self._running = False

    def kill(self) -> None:
        self._running = False

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self._running = False
        return 0


def _pair(role: str, number: int = 1) -> BridgeGenerationPair:
    issued = datetime.now(timezone.utc).isoformat()
    source = BridgeGenerationCustodyRecord(
        f"{role}-source", f"{role}-source-{number}",
        f"credential-store:{role}/source-{number}", "fixture-authority",
        issued, "a" * 64, None)
    acknowledgment = BridgeGenerationCustodyRecord(
        f"{role}-ack", f"{role}-ack-{number}",
        f"credential-store:{role}/ack-{number}", "fixture-authority",
        issued, "b" * 64, None)
    return BridgeGenerationPair(source, acknowledgment)


def _installation(*, denied_process_role: str | None = None) -> CompanionPlatformInstallation:
    authority = object.__new__(CompanionAuthorityCallbacks)
    authority.verify_generation = lambda _digest, _record: True
    authority.authorize_process_launch = lambda role, _digest, _pair: role != denied_process_role
    return CompanionPlatformInstallation("fixture-installation", "sha256:" + "c" * 64,
        custody=object(), authority=authority)  # type: ignore[arg-type]


def _spec(role: str, directory: Path) -> CompanionProcessLaunchSpec:
    return CompanionProcessLaunchSpec(role=role,
        argv=("python", "-m", "sentientos.gaming_companion_role_entrypoint",
              "--role", role, "--manifest", str(directory / "deployment.json")),
        working_directory=str(directory),
        environment={"SENTIENTOS_COMPANION_ROLE": role})


def _role_from_argv(argv: list[str]) -> str:
    return argv[argv.index("--role") + 1]


def _launch_manifest() -> dict[str, object]:
    manifest = _reverse_mutual_tls_manifest()
    manifest.update({
        "installation_identity_ref": "installation:fixture",
        "runtime_handoff_ref": "handoff:fixture",
        "software_generation_digest": "sha256:" + "d" * 64,
    })
    return manifest


def test_installed_profiles_compose_authorized_core_first_pair_and_shutdown_order(
        tmp_path: Path) -> None:
    events: list[str] = []
    spawns: list[tuple[list[str], dict[str, str]]] = []

    def spawner(argv, *, cwd, env, **kwargs):
        del cwd, kwargs
        spawns.append((argv, env))
        return _Child(len(spawns), events)

    provider = GamingCompanionPlatformPairProcessProvider(
        installation=_installation(),
        launch_specs={"windows_edge": _spec("windows_edge", tmp_path),
                      "wsl_core": _spec("wsl_core", tmp_path)},
        generation_pair_factories={"windows_edge": lambda _previous: _pair("windows_edge"),
                                   "wsl_core": lambda _previous: _pair("wsl_core")},
        health_probes={"windows_edge": lambda _child, _spec: True,
                       "wsl_core": lambda _child, _spec: True},
        spawner=spawner, process_poll_interval_seconds=0.01,
        pair_poll_interval_seconds=0.05, system_name="Windows")

    pair = provider(_launch_manifest())
    assert type(pair) is GamingCompanionPairSupervisor
    assert spawns == []
    status = pair.start()
    assert status.state == "running"
    assert [_role_from_argv(argv) for argv, _env in spawns] == ["wsl_core", "windows_edge"]
    assert all(env["SENTIENTOS_COMPANION_ROLE"] == _role_from_argv(argv)
               for argv, env in spawns)

    pair.close()
    assert events == ["stop:2", "stop:1"]
    assert pair.status().state == "stopped"


def test_pair_provider_rejects_missing_roles_and_wrong_host_before_spawning(
        tmp_path: Path) -> None:
    spec_by_role = {role: _spec(role, tmp_path)
                    for role in ("windows_edge", "wsl_core")}
    common = {
        "installation": _installation(),
        "launch_specs": spec_by_role,
        "generation_pair_factories": {role: lambda _previous, role=role: _pair(role)
                                      for role in spec_by_role},
        "health_probes": {role: lambda _child, _spec: True for role in spec_by_role},
        "system_name": "Windows",
    }
    with pytest.raises(CompanionBridgeError, match="companion_pair_process_launch_specs_required"):
        GamingCompanionPlatformPairProcessProvider(**{**common, "launch_specs": {
            "windows_edge": spec_by_role["windows_edge"]}})

    provider = GamingCompanionPlatformPairProcessProvider(**{**common,
        "system_name": "Linux"})
    with pytest.raises(CompanionBridgeError, match="companion_pair_windows_host_required"):
        provider(_launch_manifest())


def test_pair_provider_rejects_role_profile_mismatch_before_any_spawn(tmp_path: Path) -> None:
    specs = {"windows_edge": _spec("wsl_core", tmp_path),
             "wsl_core": _spec("wsl_core", tmp_path)}
    with pytest.raises(CompanionBridgeError,
                       match="companion_pair_process_profile_role_mismatch"):
        GamingCompanionPlatformPairProcessProvider(
            installation=_installation(), launch_specs=specs,
            generation_pair_factories={role: lambda _previous, role=role: _pair(role)
                                       for role in specs},
            health_probes={role: lambda _child, _spec: True for role in specs},
            system_name="Windows")


def test_pair_provider_rejects_invalid_manifest_before_supervisor_construction(
        tmp_path: Path) -> None:
    roles = ("windows_edge", "wsl_core")
    provider = GamingCompanionPlatformPairProcessProvider(
        installation=_installation(),
        launch_specs={role: _spec(role, tmp_path) for role in roles},
        generation_pair_factories={role: lambda _previous, role=role: _pair(role)
                                   for role in roles},
        health_probes={role: lambda _child, _spec: True for role in roles},
        system_name="Windows")

    with pytest.raises(CompanionBridgeError,
                       match="companion_role_authority_reference_missing"):
        provider(_reverse_mutual_tls_manifest())


def test_edge_launch_denial_rolls_back_the_already_started_core(tmp_path: Path) -> None:
    events: list[str] = []
    spawned_roles: list[str] = []

    def spawner(argv, *, cwd, env, **kwargs):
        del cwd, env, kwargs
        role = _role_from_argv(argv)
        spawned_roles.append(role)
        return _Child(len(spawned_roles), events)

    roles = ("windows_edge", "wsl_core")
    provider = GamingCompanionPlatformPairProcessProvider(
        installation=_installation(denied_process_role="windows_edge"),
        launch_specs={role: _spec(role, tmp_path) for role in roles},
        generation_pair_factories={role: lambda _previous, role=role: _pair(role)
                                   for role in roles},
        health_probes={role: lambda _child, _spec: True for role in roles},
        spawner=spawner, process_poll_interval_seconds=0.01,
        pair_poll_interval_seconds=0.05, system_name="Windows")

    pair = provider(_launch_manifest())
    with pytest.raises(CompanionBridgeError,
                       match="companion_process_launch_authority_denied"):
        pair.start()

    assert spawned_roles == ["wsl_core"]
    assert events == ["stop:1"]
    assert pair.status().state == "failed"
