"""Per-session WSL-core output composition for the reverse avatar channel."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .gaming_companion_avatar_output import (
    AdmissionReceiptBuilder,
    BridgeChatAvatarOutputEmitter,
    MutualTLSAvatarCommandSender,
)
from .gaming_companion_bridge import CompanionBridgeError, CompanionBridgeReceiver
from .gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE, validate_manifest
from .gaming_companion_tls_transport import (
    BridgeGenerationPair,
    CompanionBridgeMutualTLSClient,
    verify_generation_pair_rotation,
)

GenerationPairLoader = Callable[[str, str], BridgeGenerationPair]
BridgeKeyReader = Callable[[str], bytes]
ClientTLSContextFactory = Callable[[str, str, str], Any]
GenerationReceiptVerifier = Callable[[str, object], bool]


@dataclass(slots=True)
class WSLCoreAvatarOutputSession:
    """One session-scoped sender; uncertain message delivery is never retried."""

    emitter: BridgeChatAvatarOutputEmitter
    _sender: MutualTLSAvatarCommandSender
    _closed: bool = False

    def close(self) -> None:
        if not self._closed:
            self._sender.close()
            self._closed = True


def build_wsl_core_avatar_output_session(*, manifest: Mapping[str, Any],
        session_id: str,
        generation_pair_loader: GenerationPairLoader,
        bridge_key_reader: BridgeKeyReader,
        client_tls_context_factory: ClientTLSContextFactory,
        generation_receipt_verifier: GenerationReceiptVerifier,
        admission_receipt_builder: AdmissionReceiptBuilder,
        previous_generation_pair: BridgeGenerationPair | None = None,
        timeout_seconds: float = 2.0) -> WSLCoreAvatarOutputSession:
    """Build one TLS-pinned WSL sender from the exact v3 custody references."""
    cfg = validate_manifest(manifest)
    if cfg["schema_version"] != SCHEMA_MUTUAL_TLS_REVERSE:
        raise CompanionBridgeError("wsl_core_avatar_reverse_manifest_v3_required")
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 128:
        raise CompanionBridgeError("wsl_core_avatar_session_id_invalid")
    reverse = cfg["reverse_avatar_tls"]
    pair = generation_pair_loader(
        reverse["source_generation_custody_reference"],
        reverse["acknowledgment_generation_custody_reference"],
    )
    if type(pair) is not BridgeGenerationPair:
        raise CompanionBridgeError("wsl_core_avatar_generation_pair_required")
    if pair.source.key_reference != reverse["source_key_custody_reference"]:
        raise CompanionBridgeError("wsl_core_avatar_source_key_reference_mismatch")
    verify_generation_pair_rotation(previous=previous_generation_pair,
        successor=pair, authority_receipt_verifier=generation_receipt_verifier)
    source_key = bridge_key_reader(pair.source.key_reference)
    acknowledgment_key = bridge_key_reader(pair.acknowledgment.key_reference)
    if (not isinstance(source_key, bytes) or not isinstance(acknowledgment_key, bytes)
            or len(source_key) < 32 or len(acknowledgment_key) < 32):
        raise CompanionBridgeError("wsl_core_avatar_bridge_key_unavailable")
    tls_context = client_tls_context_factory(
        reverse["ca_bundle_reference"],
        reverse["wsl_core_client_certificate_reference"],
        reverse["wsl_core_client_private_key_reference"],
    )
    acknowledgment_receiver = CompanionBridgeReceiver(
        source_keys={pair.acknowledgment.source_id: acknowledgment_key},
        expected_generations={pair.acknowledgment.source_id:
            pair.acknowledgment.generation_id},
    )
    client = CompanionBridgeMutualTLSClient(
        address=reverse["windows_bind_address"],
        port=reverse["port"],
        server_hostname=reverse["server_hostname"],
        tls_context=tls_context,
        acknowledgment_receiver=acknowledgment_receiver,
        expected_server_certificate_sha256=(
            reverse["expected_windows_edge_server_certificate_sha256"]),
        timeout_seconds=timeout_seconds,
    )
    sender = MutualTLSAvatarCommandSender(
        client=client,
        source_id=pair.source.source_id,
        session_id=session_id,
        generation_id=pair.source.generation_id,
        source_key=source_key,
        admission_receipt_builder=admission_receipt_builder,
    )
    return WSLCoreAvatarOutputSession(
        emitter=BridgeChatAvatarOutputEmitter(sender), _sender=sender)


__all__ = ["WSLCoreAvatarOutputSession", "build_wsl_core_avatar_output_session"]
