from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import time
from datetime import datetime, timezone
import shutil
import subprocess

import pytest

from sentientos.avatar_renderer_report_ingress import renderer_report_world_state_record
from sentientos.avatar_renderer_report_ingress import RendererReportCaptureOwner, RendererReportEvidenceStore
from sentientos.avatar_renderer_report_relay import WindowsRendererReportRelay
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_tls_transport import (
    CompanionBridgeMutualTLSClient,
    CompanionBridgeMutualTLSRuntime,
)
from tests.test_gaming_companion_tls_transport import _certificate_bundle

pytestmark = pytest.mark.no_legacy_skip


def test_real_godot_demo_emits_bounded_renderer_self_report(tmp_path: Path) -> None:
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot is not installed in this validation environment")
    repository_root = Path(__file__).resolve().parents[1]
    project = repository_root / "godot_avatar_demo"
    probe = "res://tests/renderer_report_probe.gd"
    environment = dict(os.environ)
    environment.update({
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "SENTIENTOS_RENDERER_GENERATION_ID": "godot-demo-probe-generation-1",
    })
    relay = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    relay.bind(("127.0.0.1", 0))
    relay.settimeout(2.0)
    environment["SENTIENTOS_RENDERER_REPORT_RELAY_PORT"] = str(relay.getsockname()[1])

    try:
        result = subprocess.run(
            [godot, "--headless", "--path", str(project), "--script", probe],
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
            check=False,
        )
        packet, peer = relay.recvfrom(60_001)
    finally:
        relay.close()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "godot_renderer_report_probe_passed" in result.stdout
    assert "SCRIPT ERROR" not in result.stdout + result.stderr
    report_lines = [line for line in result.stdout.splitlines()
                    if line.startswith("sentientos_renderer_report_json:")]
    assert len(report_lines) == 1, result.stdout + result.stderr
    renderer_report = json.loads(report_lines[0].split(":", 1)[1])
    assert peer[0] == "127.0.0.1"
    assert json.loads(packet) == renderer_report
    assert renderer_report["renderer_generation_id"] == "godot-demo-probe-generation-1"
    record = renderer_report_world_state_record(renderer_report)
    assert record["payload"]["renderer_report"]["renderer_state"]["motion"]["active_motion"] == "wave"
    assert record["effect_proven"] is False
    assert record["payload"]["observer_issuer_posture"] == "unverified_caller_assertion"


def test_godot_uses_real_tts_boundaries_to_open_and_interrupt_avatar_mouth(tmp_path: Path) -> None:
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot is not installed in this validation environment")
    project = Path(__file__).resolve().parents[1] / "godot_avatar_demo"
    environment = dict(os.environ)
    environment.update({"XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data")})
    result = subprocess.run([godot, "--headless", "--path", str(project),
        "--script", "res://tests/speech_activity_probe.gd"], capture_output=True,
        text=True, timeout=30, env=environment, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sentientos_speech_activity_probe_passed" in result.stdout
    assert "SCRIPT ERROR" not in result.stdout + result.stderr


def test_godot_demo_udp_listener_is_explicitly_loopback_only() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    driver = (repository_root / "godot_avatar_demo/scripts/avatar_driver.gd").read_text(
        encoding="utf-8")
    assert 'const LOOPBACK_BIND_ADDRESS := "127.0.0.1"' in driver
    assert "_server.listen(listen_port, LOOPBACK_BIND_ADDRESS)" in driver
    assert "_server.listen(listen_port)" not in driver


def test_godot_report_reaches_durable_capture_through_edge_relay_and_mtls(tmp_path: Path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot is not installed in this validation environment")
    repository_root = Path(__file__).resolve().parents[1]
    project = repository_root / "godot_avatar_demo"
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    source_key, acknowledgment_key = b"r" * 32, b"a" * 32
    receiver = CompanionBridgeReceiver(source_keys={"windows-renderer-relay": source_key},
        expected_generations={"windows-renderer-relay": "edge-generation-1"})
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=receiver, acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=acknowledgment_key)
    store = RendererReportEvidenceStore(tmp_path / "captures")
    owner = RendererReportCaptureOwner(runtime=runtime, store=store)
    owner.start()
    port = runtime.status().port
    assert port is not None
    acknowledgment_receiver = CompanionBridgeReceiver(
        source_keys={"sentientos-core": acknowledgment_key},
        expected_generations={"sentientos-core": "core-generation-1"})
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=acknowledgment_receiver)
    relay = WindowsRendererReportRelay(client=client, source_id="windows-renderer-relay",
        session_id="godot-renderer-session", generation_id="edge-generation-1",
        source_key=source_key, renderer_generation_id="godot-demo-e2e-generation-1")
    relay_port = relay.start()
    environment = dict(os.environ)
    environment.update({"XDG_CACHE_HOME": str(tmp_path / "e2e-cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "e2e-config"),
        "XDG_DATA_HOME": str(tmp_path / "e2e-data"),
        "SENTIENTOS_RENDERER_GENERATION_ID": "godot-demo-e2e-generation-1",
        "SENTIENTOS_RENDERER_REPORT_RELAY_PORT": str(relay_port)})
    try:
        result = subprocess.run([godot, "--headless", "--path", str(project),
            "--script", "res://tests/renderer_report_probe.gd"], capture_output=True,
            text=True, timeout=30, env=environment, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        report_line = next(line for line in result.stdout.splitlines()
            if line.startswith("sentientos_renderer_report_json:"))
        renderer_report = json.loads(report_line.split(":", 1)[1])
        deadline = time.monotonic() + 3.0
        while (owner.status()["captured"] == 0 or relay.status().forwarded == 0) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert relay.status().forwarded == 1
        assert owner.status()["captured"] == 1
        record = store.world_state_records()[0]
        assert record["payload"]["renderer_report"] == renderer_report
        assert record["payload"]["transport_authentication_principal"] == "windows-renderer-relay"
        assert record["payload"]["renderer_source_independently_authenticated"] is False
        assert record["payload"]["renderer_state_independently_observed"] is False
        assert record["effect_proven"] is False
    finally:
        relay.close()
        owner.close()
