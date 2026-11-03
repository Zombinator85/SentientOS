from __future__ import annotations

import ssl
from datetime import datetime, timezone
from pathlib import Path

import pytest
pytestmark = pytest.mark.no_legacy_skip

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE
from sentientos.gaming_companion_edge_runtime import build_windows_edge_avatar_runtime
from sentientos.gaming_companion_receipt_replay import (
    SQLiteAdmissionReceiptReplayGuard,
)
from sentientos.gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
)
from tests.test_gaming_companion_deployment import _reverse_mutual_tls_manifest
from tests.test_gaming_companion_tls_transport import _certificate_bundle


def _generation_pair() -> BridgeGenerationPair:
    stamp = datetime.now(timezone.utc).isoformat()
    source = BridgeGenerationCustodyRecord(
        source_id="sentientos-wsl-core", generation_id="wsl-core-avatar-1",
        key_reference="credential-store:sentientos/wsl-core-avatar-source",
        issuer_id="operator-control-plane", issued_at=stamp,
        authority_receipt_digest="a" * 64, predecessor_generation_id=None,
    )
    acknowledgment = BridgeGenerationCustodyRecord(
        source_id="sentientos-windows-edge", generation_id="windows-edge-avatar-1",
        key_reference="credential-store:sentientos/windows-edge-avatar-ack",
        issuer_id="operator-control-plane", issued_at=stamp,
        authority_receipt_digest="b" * 64, predecessor_generation_id=None,
    )
    return BridgeGenerationPair(source, acknowledgment)


def test_edge_runtime_factory_resolves_only_v3_reverse_custody_and_builds_stopped_owner(
        tmp_path: Path) -> None:
    manifest = _reverse_mutual_tls_manifest()
    assert manifest["schema_version"] == SCHEMA_MUTUAL_TLS_REVERSE
    server_context, _, _ = _certificate_bundle(tmp_path)
    pair = _generation_pair()
    calls: list[tuple[object, ...]] = []

    def load_pair(source_ref: str, acknowledgment_ref: str) -> BridgeGenerationPair:
        calls.append(("pair", source_ref, acknowledgment_ref))
        return pair

    def read_key(reference: str) -> bytes:
        calls.append(("key", reference))
        return b"s" * 32 if reference == pair.source.key_reference else b"a" * 32

    def tls_factory(ca_ref: str, cert_ref: str, key_ref: str) -> ssl.SSLContext:
        calls.append(("tls", ca_ref, cert_ref, key_ref))
        return server_context

    owner = build_windows_edge_avatar_runtime(
        manifest=manifest,
        generation_pair_loader=load_pair,
        bridge_key_reader=read_key,
        server_tls_context_factory=tls_factory,
        generation_receipt_verifier=lambda _digest, _record: True,
        command_receipt_verifier=lambda _receipt, _digest, _message: True,
        renderer_sink=lambda _payload, _message: True,
    )

    status = owner.status()
    assert status.state == "stopped"
    assert status.listener_port is None
    assert status.authority_effects_performed is False
    assert status.renderer_effect_proven is False
    assert calls[0] == ("pair",
        "operator-ledger:wsl-core-avatar-generation",
        "operator-ledger:windows-edge-avatar-generation")
    assert ("key", pair.source.key_reference) in calls
    assert ("key", pair.acknowledgment.key_reference) in calls
    assert calls[-1] == ("tls",
        "windows:credential-store/bridge-ca",
        "windows:credential-store/edge-server-cert",
        "windows:dpapi/edge-server-key")


def test_edge_runtime_factory_requires_generation_receipts_before_reading_keys(tmp_path: Path) -> None:
    server_context, _, _ = _certificate_bundle(tmp_path)
    pair = _generation_pair()
    reads: list[str] = []
    with pytest.raises(CompanionBridgeError,
                       match="bridge_generation_authority_receipt_unverified"):
        build_windows_edge_avatar_runtime(
            manifest=_reverse_mutual_tls_manifest(),
            generation_pair_loader=lambda _source, _ack: pair,
            bridge_key_reader=lambda reference: reads.append(reference) or b"k" * 32,
            server_tls_context_factory=lambda _ca, _cert, _key: server_context,
            generation_receipt_verifier=lambda _digest, _record: False,
            command_receipt_verifier=lambda _receipt, _digest, _message: True,
            renderer_sink=lambda _payload, _message: True,
        )
    assert reads == []


def test_edge_runtime_factory_wires_optional_durable_receipt_guard(tmp_path: Path) -> None:
    manifest = _reverse_mutual_tls_manifest()
    server_context, _, _ = _certificate_bundle(tmp_path)
    pair = _generation_pair()
    guard = SQLiteAdmissionReceiptReplayGuard(
        tmp_path / "edge-receipt-replay.sqlite3", max_receipts=4)

    owner = build_windows_edge_avatar_runtime(
        manifest=manifest,
        generation_pair_loader=lambda _source, _ack: pair,
        bridge_key_reader=lambda reference: (
            b"s" * 32 if reference == pair.source.key_reference else b"a" * 32
        ),
        server_tls_context_factory=lambda _ca, _cert, _key: server_context,
        generation_receipt_verifier=lambda _digest, _record: True,
        command_receipt_verifier=lambda _receipt, _digest, _message: True,
        renderer_sink=lambda _payload, _message: True,
        receipt_replay_guard=guard,
    )

    assert owner.status().state == "stopped"
    assert owner.status().listener_port is None
    assert owner.status().authority_effects_performed is False
    assert owner._dispatcher._receipt_replay_guard is guard
