from __future__ import annotations

import ipaddress
import hashlib
import json
import os
import socket
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from sentientos.gaming_companion_bridge import CompanionBridgeReceiver, encode_message
from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (
    HostObservationCollectorSpec,
    HostResourceRuntimeCoordinator,
    build_observation_plan,
)
from sentientos.avatar_renderer_report_ingress import RendererReportCaptureOwner
from sentientos.avatar_renderer_report_relay import WindowsRendererReportRelay
from sentientos.foreground_game_bridge import (
    BridgeForegroundGameDetector,
    WindowsForegroundBridgePublisher,
)
from sentientos.game_performance_bridge import (
    GamePerformanceBridgeDetector,
    WindowsGamePerformanceBridgePublisher,
)
from sentientos.foreground_game_detection import ForegroundGameDetector
from sentientos.gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
    CompanionBridgeMutualTLSClient,
    CompanionBridgeMutualTLSRuntime,
    CompanionBridgeTransportError,
    read_posix_bridge_source_key,
    verify_generation_rotation,
    verify_generation_pair_rotation,
)
from sentientos.runtime_governor import PressureSnapshot, RuntimeGovernor
from sentientos.windows_game_performance import WindowsGamePerformanceObserver

pytestmark = pytest.mark.no_legacy_skip

from tests.test_avatar_renderer_report_ingress import _refresh_digest, _report


def _certificate_bundle(root: Path):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SentientOS test CA")])
    ca_cert = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256()))
    ca_path = root / "ca.pem"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    def leaf(name: str, usage: x509.ObjectIdentifier, san: x509.GeneralName | None = None):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.ExtendedKeyUsage([usage]), critical=False))
        if san is not None:
            builder = builder.add_extension(x509.SubjectAlternativeName([san]), critical=False)
        cert = builder.sign(ca_key, hashes.SHA256())
        cert_path, key_path = root / f"{name}.pem", root / f"{name}.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        return cert_path, key_path

    server_cert, server_key = leaf("server", ExtendedKeyUsageOID.SERVER_AUTH,
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    client_cert, client_key = leaf("client", ExtendedKeyUsageOID.CLIENT_AUTH)
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = ssl.TLSVersion.TLSv1_2
    server.verify_mode = ssl.CERT_REQUIRED
    server.load_verify_locations(cafile=str(ca_path))
    server.load_cert_chain(str(server_cert), str(server_key))
    client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca_path))
    client.minimum_version = ssl.TLSVersion.TLSv1_2
    client.load_cert_chain(str(client_cert), str(client_key))
    client_certificate = x509.load_pem_x509_certificate(client_cert.read_bytes())
    from cryptography.hazmat.primitives.serialization import Encoding
    return server, client, __import__("hashlib").sha256(
        client_certificate.public_bytes(Encoding.DER)).hexdigest()


def test_mutual_tls_protects_authenticated_bounded_bridge_delivery(tmp_path: Path):
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate((tmp_path / "server.pem").read_bytes())
    server_pin = hashlib.sha256(
        server_certificate.public_bytes(serialization.Encoding.DER)).hexdigest()
    source_key, ack_key = b"s" * 32, b"k" * 32
    receiver = CompanionBridgeReceiver(source_keys={"windows-edge": source_key},
        expected_generations={"windows-edge": "edge-generation-1"})
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=receiver,
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=ack_key)
    port = runtime.start()
    ack_receiver = CompanionBridgeReceiver(source_keys={"wsl-core": ack_key},
        expected_generations={"wsl-core": "core-generation-1"})
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=ack_receiver,
        expected_server_certificate_sha256=server_pin)
    now = datetime.now(timezone.utc).isoformat()
    encoded = encode_message(kind="observation", source_id="windows-edge",
        session_id="session-1", generation_id="edge-generation-1", sequence=1,
        payload={"frame_time_p95_ms": 16.7}, key=source_key, created_at=now)
    try:
        acknowledgment = client.send(encoded)
        received = runtime.receive(timeout=1.0)
        assert acknowledgment.payload["disposition"] == "accepted"
        assert received.payload["frame_time_p95_ms"] == 16.7
        assert received.signed_envelope == encoded
        assert runtime.status().accepted_messages == 1
    finally:
        runtime.close()


def test_mutual_tls_server_certificate_pin_rejects_before_sending(tmp_path: Path):
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate((tmp_path / "server.pem").read_bytes())
    server_pin = hashlib.sha256(
        server_certificate.public_bytes(serialization.Encoding.DER)).hexdigest()
    wrong_pin = "f" * 64 if server_pin != "f" * 64 else "e" * 64
    source_key, acknowledgment_key = b"p" * 32, b"q" * 32
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={"windows-edge": source_key},
            expected_generations={"windows-edge": "edge-generation-1"}),
        acknowledgment_source_id="wsl-core", acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=acknowledgment_key)
    port = runtime.start()
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": acknowledgment_key},
            expected_generations={"wsl-core": "core-generation-1"}),
        expected_server_certificate_sha256=wrong_pin)
    encoded = encode_message(kind="observation", source_id="windows-edge",
        session_id="session-pin", generation_id="edge-generation-1", sequence=1,
        payload={"frame_time_p95_ms": 16.7}, key=source_key)
    try:
        with pytest.raises(CompanionBridgeTransportError,
                           match="bridge_tls_server_certificate_pin_mismatch") as caught:
            client.send(encoded)
        assert caught.value.delivery_state == "not_sent"
        assert runtime.status().accepted_messages == 0
    finally:
        runtime.close()


def test_renderer_self_report_relay_crosses_mtls_and_keeps_relay_identity_separate(tmp_path: Path):
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    source_key, acknowledgment_key = b"renderer-relay-key-32-bytes-long!!", b"renderer-ack-key-32-bytes-long!!!"
    receiver = CompanionBridgeReceiver(source_keys={"windows-renderer-relay": source_key},
        expected_generations={"windows-renderer-relay": "edge-generation-1"})
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=receiver, acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=acknowledgment_key)
    class RecordingStore:
        def __init__(self):
            self.capture_calls = []

        def capture(self, *, report, transport):
            self.capture_calls.append((dict(report), dict(transport)))
            return {"capture_id": "test-capture"}

    store = RecordingStore()
    owner = RendererReportCaptureOwner(runtime=runtime, store=store)
    owner.start()
    port = runtime.status().port
    assert port is not None
    ack_receiver = CompanionBridgeReceiver(source_keys={"sentientos-core": acknowledgment_key},
        expected_generations={"sentientos-core": "core-generation-1"})
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=ack_receiver)
    relay = WindowsRendererReportRelay(client=client, source_id="windows-renderer-relay",
        session_id="relay-session", generation_id="edge-generation-1",
        source_key=source_key, renderer_generation_id="godot-demo-12345")
    relay_port = relay.start()
    report = _report()
    report["reported_at"] = datetime.now(timezone.utc).isoformat()
    _refresh_digest(report)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.sendto(json.dumps(report, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8"), ("127.0.0.1", relay_port))
        deadline = time.monotonic() + 2
        while (relay.status().forwarded == 0 or owner.status()["captured"] == 0) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert relay.status().forwarded == 1
        assert owner.status()["captured"] == 1
        assert len(store.capture_calls) == 1
        captured_report, transport = store.capture_calls[0]
        assert transport["source_id"] == "windows-renderer-relay"
        assert transport["report_source_id"] == "godot-procedural-demo"
        assert captured_report["effect_proven"] is False
        assert captured_report["independent_observation"] is False
    finally:
        sender.close()
        relay.close()
        owner.close()


def test_windows_foreground_publisher_and_core_detector_compose_over_mutual_tls(tmp_path: Path):
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    source_key, ack_key = b"e" * 32, b"c" * 32
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={"windows-edge": source_key},
            expected_generations={"windows-edge": "edge-generation-1"}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-generation-1", acknowledgment_key=ack_key)
    port = runtime.start()
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(source_keys={"wsl-core": ack_key},
            expected_generations={"wsl-core": "core-generation-1"}))
    publisher = WindowsForegroundBridgePublisher(
        detector=ForegroundGameDetector(system_provider=lambda: "Windows",
            process_name_provider=lambda: "game.exe"),
        client=client, source_id="windows-edge", session_id="session-1",
        generation_id="edge-generation-1", source_key=source_key)
    core_detector = BridgeForegroundGameDetector(runtime=runtime,
        source_id="windows-edge", generation_id="edge-generation-1")
    try:
        acknowledgment = publisher.publish_once(["game.exe"])
        observation = core_detector.observe(["game.exe"])
        assert observation.status == "available" and observation.game_foreground is True
        assert observation.transport_provenance is not None
        assert observation.transport_provenance["message_id"] == acknowledgment.payload["message_id"]
        assert runtime.status().accepted_messages == 1
    finally:
        core_detector.close()


def test_production_game_evidence_schemas_share_one_ordered_mtls_session(
        tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    source_key, ack_key = b"e" * 32, b"c" * 32
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={"windows-edge": source_key},
            expected_generations={"windows-edge": "edge-generation-1"}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-generation-1", acknowledgment_key=ack_key)
    port = runtime.start()
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(source_keys={"wsl-core": ack_key},
            expected_generations={"wsl-core": "core-generation-1"}))
    publication_lock = threading.Lock()
    sequence = 0

    def allocate_sequence() -> int:
        nonlocal sequence
        sequence += 1
        return sequence

    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"cpu_percent": 33.0, "rss_bytes": 131072},
        frame_provider=lambda _pid: ((16.7, 20.0), "f" * 64))
    performance_publisher = WindowsGamePerformanceBridgePublisher(
        observer=observer, client=client, source_id="windows-edge",
        session_id="shared-game-evidence", generation_id="edge-generation-1",
        source_key=source_key, process_id=456, sequence_allocator=allocate_sequence,
        publication_lock=publication_lock)
    foreground_publisher = WindowsForegroundBridgePublisher(
        detector=ForegroundGameDetector(system_provider=lambda: "Windows",
            process_name_provider=lambda: "game.exe"), client=client,
        source_id="windows-edge", session_id="shared-game-evidence",
        generation_id="edge-generation-1", source_key=source_key,
        sequence_allocator=allocate_sequence, publication_lock=publication_lock)
    core_detector = BridgeForegroundGameDetector(runtime=runtime,
        source_id="windows-edge", generation_id="edge-generation-1")

    governor = RuntimeGovernor()
    monkeypatch.setattr(governor, "sample_pressure", lambda: PressureSnapshot(
        0.0, 0.0, 0.0, 0.0, 0.0, datetime.now(timezone.utc).isoformat()))
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "control-plane" / "decisions.jsonl")
    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or datetime.now(timezone.utc).isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 10.0,
                    "vram_utilization_percent": 20.0}])),
        ]))
    core_detector.set_game_performance_admission_owner(kernel)
    core_detector.set_game_workload_admission_owner(kernel)
    try:
        performance_ack = performance_publisher.publish_once()
        foreground_ack = foreground_publisher.publish_once(["game.exe"])
        assert performance_ack.sequence == 1
        assert foreground_ack.sequence == 2
        observation = core_detector.observe(["game.exe"])
        assert observation.status == "available" and observation.game_foreground is True
        performance_evidence = kernel.current_verified_game_performance_evidence()
        assert performance_evidence is not None
        assert performance_evidence["sequence"] == 1
        assert governor._game_workload_evidence is not None
        assert governor._game_workload_evidence["sequence"] == 2
        assert runtime.status().accepted_messages == 2

        def admit(observation, correlation_id):
            observation_id = "local-chat-serving-" + hashlib.sha256(
                correlation_id.encode("utf-8")).hexdigest()[:32]
            evaluation = host_owner.run_cycle(correlation_id=observation_id)
            assert evaluation is not None
            return governor._admit_local_model_inference(
                actor="chat_service", subject="local_model", correlation_id=correlation_id,
                operation_kind="model_serving", metadata={
                "resource_governance_required": True,
                "purpose": "local_model_serving",
                "host_resource_observation_namespace": "local-chat-serving",
                "host_resource_observation_id": observation_id,
                "workload_mode": "automatic",
                "model_execution_profile": {
                    "schema_version": "sentientos.model_execution_profile:v1",
                    "engine": "llama_cpp", "accelerator_route": "gpu",
                    "gpu_layers": 8, "configuration_digest": "d" * 64,
                },
                "serving_workload_evidence": {
                    "transport_provenance": {
                        "message_id": observation.transport_provenance["message_id"]}},
                })

        decision = admit(observation, "mTLS-game-serving-active")
        assert decision.allowed is False
        assert decision.reason == "deferred_gpu_model_serving_while_game_active"
        assert decision.evidence_refs["host_resource_evidence"]["status"] == "current"
        assert decision.evidence_refs["host_resource_evidence"][
            "gpu_telemetry_complete"] is True

        idle_foreground_publisher = WindowsForegroundBridgePublisher(
            detector=ForegroundGameDetector(system_provider=lambda: "Windows",
                process_name_provider=lambda: "explorer.exe",
                running_process_names_provider=lambda: ()), client=client,
            source_id="windows-edge", session_id="shared-game-evidence",
            generation_id="edge-generation-1", source_key=source_key,
            sequence_allocator=allocate_sequence, publication_lock=publication_lock)
        idle_ack = idle_foreground_publisher.publish_once(["game.exe"])
        assert idle_ack.sequence == 3
        idle_observation = core_detector.observe(["game.exe"])
        assert idle_observation.status == "available"
        assert idle_observation.game_foreground is False
        assert idle_observation.game_process_running is False
        idle_decision = admit(idle_observation, "mTLS-game-serving-idle")
        assert idle_decision.allowed is True

        resumed_ack = foreground_publisher.publish_once(["game.exe"])
        assert resumed_ack.sequence == 4
        resumed_observation = core_detector.observe(["game.exe"])
        assert resumed_observation.game_foreground is True
        resumed_decision = admit(resumed_observation, "mTLS-game-serving-resumed")
        assert resumed_decision.allowed is False
        assert resumed_decision.reason == "deferred_gpu_model_serving_while_game_active"
        assert host_owner.collector_call_count == 9
        assert runtime.status().accepted_messages == 4
    finally:
        core_detector.close()


def test_windows_game_performance_sample_crosses_mtls_and_retains_measured_lineage(tmp_path: Path):
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    source_key, ack_key = b"windows-performance-source-key-32-bytes", b"performance-ack-key-32-bytes-long"
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={"windows-edge": source_key},
            expected_generations={"windows-edge": "edge-generation-1"}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-generation-1", acknowledgment_key=ack_key)
    port = runtime.start()
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(source_keys={"wsl-core": ack_key},
            expected_generations={"wsl-core": "core-generation-1"}))
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"cpu_percent": 33.0, "rss_bytes": 131072},
        frame_provider=lambda _pid: ((16.7, 52.0), "f" * 64))
    publisher = WindowsGamePerformanceBridgePublisher(observer=observer, client=client,
        source_id="windows-edge", session_id="game-session", generation_id="edge-generation-1",
        source_key=source_key, process_id=456)
    detector = GamePerformanceBridgeDetector(receiver=runtime, source_id="windows-edge",
        generation_provider=lambda: "edge-generation-1")
    try:
        acknowledgment = publisher.publish_once()
        observation = detector.receive_once(timeout=1.0)
        assert acknowledgment.payload["disposition"] == "accepted"
        assert observation.frame_time_p95_ms == 52.0
        assert observation.hitch_count_over_50ms == 1
        assert observation.process_cpu_percent == 33.0
        assert observation.process_rss_bytes == 131072
        assert observation.generation_id == "edge-generation-1"
        assert len(observation.payload_digest) == 64
        assert runtime.status().accepted_messages == 1
    finally:
        runtime.close()


def test_mutual_tls_requires_client_certificate_validation(tmp_path: Path):
    server_context, _, peer_digest = _certificate_bundle(tmp_path)
    server_context.verify_mode = ssl.CERT_NONE
    receiver = CompanionBridgeReceiver(source_keys={"edge": b"s" * 32},
        expected_generations={"edge": "generation-1"})
    with pytest.raises(ValueError, match="mutual_tls_required"):
        CompanionBridgeMutualTLSRuntime(bind_address="192.168.1.2",
            tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
            receiver=receiver,
            acknowledgment_source_id="core", acknowledgment_generation_id="core-1",
            acknowledgment_key=b"a" * 32)


@pytest.mark.skipif(os.name != "posix", reason="POSIX key-file custody semantics")
def test_posix_bridge_key_reader_requires_private_regular_owned_file(tmp_path: Path):
    key_path = tmp_path / "source.key"
    key_path.write_bytes(b"x" * 32)
    key_path.chmod(0o600)
    assert read_posix_bridge_source_key(key_path) == b"x" * 32
    key_path.chmod(0o640)
    with pytest.raises(ValueError, match="custody_invalid"):
        read_posix_bridge_source_key(key_path)
    if hasattr(os, "symlink"):
        link = tmp_path / "key-link"
        link.symlink_to(key_path)
        with pytest.raises(ValueError, match="custody_invalid"):
            read_posix_bridge_source_key(link)


def test_generation_rotation_requires_a_new_key_generation_chain_and_verified_authority(tmp_path: Path):
    initial = BridgeGenerationCustodyRecord.from_mapping({
        "schema_version": "sentientos.companion_bridge_generation_custody:v1",
        "source_id": "windows-edge", "generation_id": "edge-generation-1",
        "key_reference": "dpapi:sentientos/edge-1", "issuer_id": "operator-control-plane",
        "issued_at": "2026-11-01T00:00:00+00:00", "authority_receipt_digest": "a" * 64,
        "predecessor_generation_id": None,
    })
    successor_mapping = {
        "schema_version": "sentientos.companion_bridge_generation_custody:v1",
        "source_id": "windows-edge", "generation_id": "edge-generation-2",
        "key_reference": "dpapi:sentientos/edge-2", "issuer_id": "operator-control-plane",
        "issued_at": "2026-11-02T00:00:00+00:00", "authority_receipt_digest": "b" * 64,
        "predecessor_generation_id": "edge-generation-1",
    }
    successor = BridgeGenerationCustodyRecord.from_mapping(successor_mapping)
    verified = []
    verify_generation_rotation(previous=initial, successor=successor,
        authority_receipt_verifier=lambda digest, record: verified.append((digest, record)) or True)
    assert verified == [("b" * 64, successor)]

    successor_path = tmp_path / "generation.json"
    successor_path.write_text(__import__("json").dumps(successor_mapping), encoding="utf-8")
    successor_path.chmod(0o600)
    assert BridgeGenerationCustodyRecord.load(successor_path) == successor
    stale = dict(successor_mapping, key_reference="dpapi:sentientos/edge-1")
    stale_record = BridgeGenerationCustodyRecord.from_mapping(stale)
    with pytest.raises(ValueError, match="rotation_chain_invalid"):
        verify_generation_rotation(previous=initial, successor=stale_record,
            authority_receipt_verifier=lambda digest, record: True)
    with pytest.raises(ValueError, match="authority_receipt_unverified"):
        verify_generation_rotation(previous=initial, successor=successor,
            authority_receipt_verifier=lambda digest, record: False)


def test_source_and_acknowledgment_generation_pair_rotates_and_loads_with_private_custody(tmp_path: Path):
    initial_source = BridgeGenerationCustodyRecord(
        "windows-edge", "edge-1", "dpapi:edge-1", "operator",
        "2026-11-01T00:00:00+00:00", "a" * 64, None)
    initial_ack = BridgeGenerationCustodyRecord(
        "sentientos-core", "core-1", "wsl:core-1", "operator",
        "2026-11-01T00:00:00+00:00", "c" * 64, None)
    successor_source = BridgeGenerationCustodyRecord(
        "windows-edge", "edge-2", "dpapi:edge-2", "operator",
        "2026-11-02T00:00:00+00:00", "b" * 64, "edge-1")
    successor_ack = BridgeGenerationCustodyRecord(
        "sentientos-core", "core-2", "wsl:core-2", "operator",
        "2026-11-02T00:00:00+00:00", "d" * 64, "core-1")
    initial = BridgeGenerationPair(initial_source, initial_ack)
    successor = BridgeGenerationPair(successor_source, successor_ack)
    verified: list[str] = []
    verify_generation_pair_rotation(previous=initial, successor=successor,
        authority_receipt_verifier=lambda digest, _record: verified.append(digest) or True)
    assert verified == ["b" * 64, "d" * 64]

    pair_path = tmp_path / "generation-pair.json"
    pair_path.write_text(__import__("json").dumps(successor.to_dict()), encoding="utf-8")
    pair_path.chmod(0o600)
    assert BridgeGenerationPair.load(pair_path) == successor
    with pytest.raises(ValueError, match="rotation_chain_invalid"):
        verify_generation_pair_rotation(previous=initial,
            successor=BridgeGenerationPair(successor_source, initial_ack),
            authority_receipt_verifier=lambda _digest, _record: True)


@pytest.mark.parametrize("address", ["0.0.0.0", "8.8.8.8", "224.0.0.1", "169.254.1.2"])
def test_protected_transport_rejects_wildcard_public_and_link_local_addresses(address: str):
    from sentientos.gaming_companion_tls_transport import _validate_private_address
    with pytest.raises(ValueError):
        _validate_private_address(address)


def test_mtls_client_distinguishes_tcp_connect_failure(tmp_path: Path, monkeypatch):
    _server_context, client_context, _peer_digest = _certificate_bundle(tmp_path)
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=1,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": b"k" * 32},
            expected_generations={"wsl-core": "core-generation-1"}))

    def refused(_self, _address):
        raise ConnectionRefusedError(111, "connection refused")

    monkeypatch.setattr(socket.socket, "connect", refused)
    encoded = encode_message(kind="observation", source_id="windows-edge",
        session_id="session-connect-failure", generation_id="edge-generation-1",
        sequence=1, payload={}, key=b"s" * 32)
    with pytest.raises(CompanionBridgeTransportError,
                       match="bridge_tls_connection_unavailable") as caught:
        client.send(encoded)
    assert caught.value.delivery_state == "not_sent"
    assert caught.value.failure_phase == "tcp_connect"
    assert caught.value.failure_type == "ConnectionRefusedError"
    assert caught.value.failure_errno == 111


def test_mtls_client_distinguishes_tls_handshake_failure(tmp_path: Path):
    _server_context, client_context, _peer_digest = _certificate_bundle(tmp_path)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = int(listener.getsockname()[1])

    def send_non_tls_response():
        connection, _address = listener.accept()
        with connection:
            connection.sendall(b"not a TLS handshake")
        listener.close()

    peer = threading.Thread(target=send_non_tls_response, daemon=True)
    peer.start()
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": b"k" * 32},
            expected_generations={"wsl-core": "core-generation-1"}))
    encoded = encode_message(kind="observation", source_id="windows-edge",
        session_id="session-handshake-failure", generation_id="edge-generation-1",
        sequence=1, payload={}, key=b"s" * 32)
    try:
        with pytest.raises(CompanionBridgeTransportError,
                           match="bridge_tls_connection_unavailable") as caught:
            client.send(encoded)
        assert caught.value.delivery_state == "not_sent"
        assert caught.value.failure_phase == "tls_handshake"
        assert caught.value.failure_type in {"SSLError", "SSLEOFError", "ConnectionAbortedError"}
    finally:
        peer.join(timeout=2)
        listener.close()
