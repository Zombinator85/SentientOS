from __future__ import annotations

import ssl
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_core_runtime import build_wsl_core_avatar_output_session
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


def test_core_avatar_session_resolves_reverse_tls_and_admission_references(tmp_path: Path) -> None:
    pair = _generation_pair()
    _, client_context, _ = _certificate_bundle(tmp_path)
    observed: list[tuple[object, ...]] = []

    def key_reader(reference: str) -> bytes:
        observed.append(("key", reference))
        return b"s" * 32 if reference == pair.source.key_reference else b"a" * 32

    def client_context_factory(ca_ref: str, cert_ref: str, key_ref: str) -> ssl.SSLContext:
        observed.append(("tls", ca_ref, cert_ref, key_ref))
        return client_context

    def receipt_builder(authorization):
        observed.append(("admission", authorization))
        return {"receipt_id": "operator-issued", "semantic_digest": "d" * 64}

    session = build_wsl_core_avatar_output_session(
        manifest=_reverse_mutual_tls_manifest(),
        session_id="chat-session-9",
        generation_pair_loader=lambda source_ref, ack_ref: (
            observed.append(("pair", source_ref, ack_ref)) or pair),
        bridge_key_reader=key_reader,
        client_tls_context_factory=client_context_factory,
        generation_receipt_verifier=lambda _digest, _record: True,
        admission_receipt_builder=receipt_builder,
    )
    assert session.emitter is not None
    assert observed[0] == ("pair",
        "operator-ledger:wsl-core-avatar-generation",
        "operator-ledger:windows-edge-avatar-generation")
    assert ("key", pair.source.key_reference) in observed
    assert ("key", pair.acknowledgment.key_reference) in observed
    assert observed[-1] == ("tls",
        "windows:credential-store/bridge-ca",
        "wsl:/etc/sentientos/bridge/core-client.pem",
        "wsl:/etc/sentientos/bridge/core-client.key")
    session.close()
    session.close()


def test_core_avatar_session_checks_generation_authority_before_key_reads(tmp_path: Path) -> None:
    pair = _generation_pair()
    _, client_context, _ = _certificate_bundle(tmp_path)
    reads: list[str] = []
    with pytest.raises(CompanionBridgeError,
                       match="bridge_generation_authority_receipt_unverified"):
        build_wsl_core_avatar_output_session(
            manifest=_reverse_mutual_tls_manifest(),
            session_id="chat-session-9",
            generation_pair_loader=lambda _source, _ack: pair,
            bridge_key_reader=lambda reference: reads.append(reference) or b"k" * 32,
            client_tls_context_factory=lambda _ca, _cert, _key: client_context,
            generation_receipt_verifier=lambda _digest, _record: False,
            admission_receipt_builder=lambda _authorization: {
                "receipt_id": "must-not-run", "semantic_digest": "e" * 64},
        )
    assert reads == []
