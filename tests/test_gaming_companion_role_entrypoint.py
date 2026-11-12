from __future__ import annotations

import json
import threading
from typing import Any, Mapping, cast
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_core_runtime import WSLCoreGamingCompanionRuntime
from sentientos.gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE
from sentientos.gaming_companion_edge_runtime import WindowsEdgeAvatarRuntime
from sentientos.gaming_companion_avatar_output import AvatarCommandDispatchStatus
from sentientos.foreground_game_bridge import BridgeForegroundGameDetector
from sentientos.gaming_companion_core_runtime import WSLCoreAvatarOutputSession
from sentientos.gaming_companion_role_entrypoint import (
    compose_authorized_runtime,
    load_role_manifest,
    resolve_provider,
    runtime_is_healthy,
    run_role,
)

pytestmark = pytest.mark.no_legacy_skip


def _manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_MUTUAL_TLS_REVERSE,
        "deployment_id": "role-entry-fixture",
        "repository_root": "/home/operator/SentientOS",
        "python_executable": "/home/operator/SentientOS/.venv/bin/python",
        "state_root": "/home/operator/.local/share/sentientos",
        "installation_identity_ref": "installation:role-fixture",
        "serving_operation_ref": None,
        "runtime_handoff_ref": "runtime-handoff:role-fixture",
        "software_generation_digest": "sha256:" + "a" * 64,
        "enabled_windows_components": ["foreground_observer", "godot_renderer"],
        "bridge_key_reference": "credential-store:sentientos/windows-edge-source",
        "bridge_bind_scope": "mutual_tls_private",
        "firewall_rule_reference": "operator-firewall-rule:sentientos-wsl-core",
        "bridge_tls": {
            "schema_version": "sentientos.companion_bridge_mtls:v1",
            "core_bind_address": "172.20.0.1", "port": 54321,
            "server_hostname": "sentientos-wsl-core",
            "ca_bundle_reference": "wsl:/etc/sentientos/bridge/ca.pem",
            "core_certificate_reference": "wsl:/etc/sentientos/bridge/core.pem",
            "core_private_key_reference": "wsl:/etc/sentientos/bridge/core.key",
            "windows_edge_client_certificate_reference": "windows:credential-store/edge-cert",
            "windows_edge_client_private_key_reference": "windows:dpapi/edge-key",
            "expected_windows_edge_certificate_sha256": "a" * 64,
            "source_key_custody_reference": "credential-store:sentientos/windows-edge-source",
            "source_generation_custody_reference": "operator-ledger:windows-edge-generation",
            "acknowledgment_generation_custody_reference": "operator-ledger:wsl-core-generation",
        },
        "reverse_avatar_tls": {
            "schema_version": "sentientos.companion_avatar_reverse_mtls:v1",
            "windows_bind_address": "192.168.1.42", "port": 54322,
            "server_hostname": "sentientos-windows-edge",
            "ca_bundle_reference": "windows:credential-store/bridge-ca",
            "windows_edge_certificate_reference": "windows:credential-store/edge-server-cert",
            "windows_edge_private_key_reference": "windows:dpapi/edge-server-key",
            "wsl_core_client_certificate_reference": "wsl:/etc/sentientos/bridge/core-client.pem",
            "wsl_core_client_private_key_reference": "wsl:/etc/sentientos/bridge/core-client.key",
            "expected_wsl_core_certificate_sha256": "b" * 64,
            "expected_windows_edge_server_certificate_sha256": "c" * 64,
            "source_key_custody_reference": "credential-store:sentientos/wsl-core-avatar-source",
            "source_generation_custody_reference": "operator-ledger:wsl-core-avatar-generation",
            "acknowledgment_generation_custody_reference": "operator-ledger:windows-edge-avatar-generation",
        },
        "reverse_firewall_rule_reference": "operator-firewall-rule:sentientos-windows-edge",
        "start_on_login": False,
        "automatic_capture": False,
        "automatic_speech": False,
    }


class _CoreBridge:
    def __init__(self, *, running: bool = True) -> None:
        self.running = running
        self.started = 0
        self.closed = 0

    def start(self) -> int:
        self.started += 1
        return 54321

    def status(self) -> SimpleNamespace:
        return SimpleNamespace(running=self.running, accepted_messages=0,
            rejected_connections=0)

    def close(self) -> None:
        self.closed += 1


class _EdgeListener:
    def __init__(self) -> None:
        self.closed = 0

    def start(self) -> int:
        return 54322

    def close(self) -> None:
        self.closed += 1


class _EdgeDispatcher:
    def __init__(self) -> None:
        self.running = False

    def start(self) -> None:
        self.running = True

    def close(self) -> None:
        self.running = False

    def status(self) -> AvatarCommandDispatchStatus:
        return AvatarCommandDispatchStatus("running" if self.running else "stopped",
            0, 0, 0, None, None)


class _Closable:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def _core_runtime(bridge: _CoreBridge) -> tuple[WSLCoreGamingCompanionRuntime, _Closable]:
    session = _Closable()
    runtime = WSLCoreGamingCompanionRuntime(
        foreground_game_detector=cast(BridgeForegroundGameDetector, _Closable()),
        avatar_output_session=cast(WSLCoreAvatarOutputSession, session),
        _bridge_runtime=bridge,  # type: ignore[arg-type]
    )
    return runtime, session


def test_role_runner_owns_core_lifetime_and_stops_cleanly() -> None:
    bridge = _CoreBridge()
    runtime, session = _core_runtime(bridge)
    stop = threading.Event()
    stop.set()
    seen: list[tuple[str, str]] = []

    def provider(role: str, config: Mapping[str, Any]) -> object:
        seen.append((role, str(config["deployment_id"])))
        return runtime

    result = run_role(role="wsl_core", manifest=_manifest(),
        runtime_provider=provider,
        launch_authorizer=lambda _role, _config: True,
        stop_event=stop, poll_interval_seconds=0.05, system_name="Linux", is_wsl=True)

    assert result == 0
    assert seen == [("wsl_core", "role-entry-fixture")]
    assert bridge.started == 1 and bridge.closed == 1
    assert session.closed == 1


def test_authorized_runtime_composition_reuses_installed_role_boundary() -> None:
    bridge = _CoreBridge()
    runtime, _session = _core_runtime(bridge)
    events: list[str] = []
    composed = compose_authorized_runtime(role="wsl_core", manifest=_manifest(),
        runtime_provider=lambda role, _config: events.append("provider:" + role) or runtime,
        launch_authorizer=lambda role, _config: events.append("authorize:" + role) or True,
        system_name="Linux", is_wsl=True)
    assert composed is runtime
    assert events == ["authorize:wsl_core", "provider:wsl_core"]
    assert bridge.started == bridge.closed == 0


def test_role_runner_fails_closed_and_closes_when_listener_becomes_unhealthy() -> None:
    bridge = _CoreBridge(running=False)
    runtime, session = _core_runtime(bridge)
    result = run_role(role="wsl_core", manifest=_manifest(),
        runtime_provider=lambda _role, _config: runtime,
        launch_authorizer=lambda _role, _config: True,
        stop_event=threading.Event(), poll_interval_seconds=0.05,
        system_name="Linux", is_wsl=True)
    assert result == 3
    assert bridge.started == 1 and bridge.closed == 1
    assert session.closed == 1


def test_role_runner_owns_windows_edge_lifetime() -> None:
    listener = _EdgeListener()
    dispatcher = _EdgeDispatcher()
    runtime = WindowsEdgeAvatarRuntime(runtime=listener, dispatcher=dispatcher)  # type: ignore[arg-type]
    stop = threading.Event()
    stop.set()
    result = run_role(role="windows_edge", manifest=_manifest(),
        runtime_provider=lambda _role, _config: runtime,
        launch_authorizer=lambda _role, _config: True,
        stop_event=stop, poll_interval_seconds=0.05, system_name="Windows")
    assert result == 0
    assert listener.closed == 1
    assert not dispatcher.running


def test_configured_game_performance_publisher_participates_in_edge_health() -> None:
    listener = _EdgeListener()
    dispatcher = _EdgeDispatcher()
    runtime = WindowsEdgeAvatarRuntime(runtime=listener, dispatcher=dispatcher)  # type: ignore[arg-type]
    runtime.start()

    class Pump:
        running = False

        def status(self) -> dict[str, object]:
            return {"running": self.running}

        def close(self) -> None:
            self.running = False

    pump = Pump()
    runtime._game_performance_pump = cast(Any, pump)
    assert not runtime_is_healthy("windows_edge", runtime)
    pump.running = True
    assert runtime_is_healthy("windows_edge", runtime)
    runtime.close()


def test_configured_foreground_game_publisher_participates_in_edge_health() -> None:
    listener = _EdgeListener()
    dispatcher = _EdgeDispatcher()
    runtime = WindowsEdgeAvatarRuntime(runtime=listener, dispatcher=dispatcher)  # type: ignore[arg-type]
    runtime.start()

    class Pump:
        running = False

        def status(self):
            return SimpleNamespace(running=self.running)

        def close(self) -> None:
            self.running = False

    pump = Pump()
    runtime._foreground_game_pump = cast(Any, pump)
    assert not runtime_is_healthy("windows_edge", runtime)
    pump.running = True
    assert runtime_is_healthy("windows_edge", runtime)
    runtime.close()


def test_unsupported_host_does_not_invoke_or_import_provider() -> None:
    called = False

    def provider(_role: str, _manifest: Mapping[str, Any]) -> object:
        nonlocal called
        called = True
        return object()

    with pytest.raises(CompanionBridgeError, match="companion_role_windows_required"):
        run_role(role="windows_edge", manifest=_manifest(), runtime_provider=provider,
            launch_authorizer=lambda _role, _config: True,
            stop_event=threading.Event(), system_name="Linux", is_wsl=True)
    assert called is False


def test_launch_authority_denial_prevents_runtime_resolution() -> None:
    called = False

    def provider(_role: str, _manifest: Mapping[str, Any]) -> object:
        nonlocal called
        called = True
        return object()

    with pytest.raises(CompanionBridgeError, match="companion_role_launch_authority_denied"):
        run_role(role="wsl_core", manifest=_manifest(), runtime_provider=provider,
            launch_authorizer=lambda _role, _config: False,
            stop_event=threading.Event(), system_name="Linux", is_wsl=True)
    assert called is False


def test_runtime_type_mismatch_is_rejected_without_invoking_untrusted_close() -> None:
    closed = False

    class UnexpectedRuntime:
        def close(self) -> None:
            nonlocal closed
            closed = True

    with pytest.raises(CompanionBridgeError, match="companion_role_runtime_type_mismatch"):
        run_role(role="wsl_core", manifest=_manifest(),
            runtime_provider=lambda _role, _config: UnexpectedRuntime(),
            launch_authorizer=lambda _role, _config: True,
            stop_event=threading.Event(), system_name="Linux", is_wsl=True)
    assert closed is False


def test_missing_runtime_identity_blocks_before_authority_provider() -> None:
    manifest = _manifest()
    manifest["runtime_handoff_ref"] = None
    called = False

    def authorizer(_role: str, _config: Mapping[str, Any]) -> bool:
        nonlocal called
        called = True
        return True

    with pytest.raises(CompanionBridgeError, match="companion_role_authority_reference_missing"):
        run_role(role="wsl_core", manifest=manifest,
            runtime_provider=lambda _role, _config: object(),
            launch_authorizer=authorizer, stop_event=threading.Event(),
            system_name="Linux", is_wsl=True)
    assert called is False


def test_manifest_loader_rejects_symlink_and_invalid_json(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_manifest()), encoding="utf-8")
    alias = tmp_path / "alias.json"
    alias.symlink_to(target)
    with pytest.raises(CompanionBridgeError, match="companion_role_manifest_path_invalid"):
        load_role_manifest(alias)
    target.write_text("not json", encoding="utf-8")
    with pytest.raises(CompanionBridgeError, match="companion_role_manifest_unreadable"):
        load_role_manifest(target)


def test_manifest_loader_rejects_oversized_input_before_json_parse(tmp_path: Path) -> None:
    target = tmp_path / "oversized.json"
    target.write_bytes(b" " * (1_048_576 + 1))
    with pytest.raises(CompanionBridgeError,
                       match="companion_role_manifest_size_or_type_invalid"):
        load_role_manifest(target)


def test_manifest_loader_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    target = tmp_path / "duplicate.json"
    target.write_text('{"schema_version":"sentientos.gaming_companion_deployment:v3",'
        '"schema_version":"sentientos.gaming_companion_deployment:v3"}', encoding="utf-8")
    with pytest.raises(CompanionBridgeError,
                       match="companion_role_manifest_duplicate_field"):
        load_role_manifest(target)


@pytest.mark.parametrize("reference", ["../outside:factory", "pkg:bad-name", "pkg", "pkg:factory;exec"])
def test_provider_reference_is_closed(reference: str) -> None:
    with pytest.raises(CompanionBridgeError, match="companion_role_provider_reference_invalid"):
        resolve_provider(reference)
