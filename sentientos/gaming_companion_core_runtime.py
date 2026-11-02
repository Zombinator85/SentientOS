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
from .foreground_game_bridge import BridgeForegroundGameDetector
from .gaming_companion_tls_transport import (
    BridgeGenerationPair,
    CompanionBridgeMutualTLSClient,
    CompanionBridgeMutualTLSRuntime,
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


@dataclass(slots=True)
class WSLCoreGamingCompanionRuntime:
    """Own both authenticated bridge directions for a WSL core process."""

    foreground_game_detector: BridgeForegroundGameDetector
    avatar_output_session: WSLCoreAvatarOutputSession
    _bridge_runtime: CompanionBridgeMutualTLSRuntime
    _state: str = "stopped"
    _port: int | None = None

    def start(self) -> dict[str, object]:
        if self._state != "stopped":
            raise CompanionBridgeError("wsl_core_companion_runtime_already_started")
        self._state = "starting"
        try:
            self._port = self._bridge_runtime.start()
        except Exception:
            self._state = "failed"
            raise
        self._state = "running"
        return self.status()

    def status(self) -> dict[str, object]:
        bridge = self._bridge_runtime.status()
        return {"state": self._state, "forward_listener_running": bridge.running,
            "forward_listener_port": self._port, "accepted_observations": bridge.accepted_messages,
            "rejected_connections": bridge.rejected_connections,
            "authority_effects_performed": False}

    def close(self) -> None:
        if self._state == "stopped":
            self.avatar_output_session.close()
            self._bridge_runtime.close()
            return
        self._state = "stopping"
        try:
            self.avatar_output_session.close()
        finally:
            self._bridge_runtime.close()
            self._port = None
            self._state = "stopped"


def build_wsl_core_avatar_output_session(*, manifest: Mapping[str, Any],
        session_id: str | None = None,
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
    if (session_id is not None
            and (not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 128)):
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


def build_wsl_core_gaming_companion_runtime(*, manifest: Mapping[str, Any],
        generation_pair_loader: GenerationPairLoader,
        bridge_key_reader: BridgeKeyReader,
        server_tls_context_factory: Callable[[str, str, str], Any],
        client_tls_context_factory: ClientTLSContextFactory,
        generation_receipt_verifier: GenerationReceiptVerifier,
        admission_receipt_builder: AdmissionReceiptBuilder,
        previous_forward_generation_pair: BridgeGenerationPair | None = None,
        previous_reverse_generation_pair: BridgeGenerationPair | None = None,
        session_id: str | None = None,
        timeout_seconds: float = 2.0,
        max_observation_age_seconds: float = 5.0) -> WSLCoreGamingCompanionRuntime:
    """Compose the full WSL networking edge without starting a target listener.

    Windows game observations enter through the forward listener and are exposed
    as a verified foreground detector. Governed avatar output returns through a
    separately custodied reverse sender. All platform state and authority remain
    supplied by the injected custody adapters.
    """
    cfg = validate_manifest(manifest)
    if cfg["schema_version"] != SCHEMA_MUTUAL_TLS_REVERSE:
        raise CompanionBridgeError("wsl_core_companion_manifest_v3_required")
    forward = cfg["bridge_tls"]
    pair = generation_pair_loader(
        forward["source_generation_custody_reference"],
        forward["acknowledgment_generation_custody_reference"],
    )
    if type(pair) is not BridgeGenerationPair:
        raise CompanionBridgeError("wsl_core_companion_generation_pair_required")
    if pair.source.key_reference != forward["source_key_custody_reference"]:
        raise CompanionBridgeError("wsl_core_companion_source_key_reference_mismatch")
    verify_generation_pair_rotation(previous=previous_forward_generation_pair,
        successor=pair, authority_receipt_verifier=generation_receipt_verifier)
    source_key = bridge_key_reader(pair.source.key_reference)
    acknowledgment_key = bridge_key_reader(pair.acknowledgment.key_reference)
    if (not isinstance(source_key, bytes) or not isinstance(acknowledgment_key, bytes)
            or len(source_key) < 32 or len(acknowledgment_key) < 32):
        raise CompanionBridgeError("wsl_core_companion_bridge_key_unavailable")
    server_context = server_tls_context_factory(
        forward["ca_bundle_reference"],
        forward["core_certificate_reference"],
        forward["core_private_key_reference"],
    )
    receiver = CompanionBridgeReceiver(
        source_keys={pair.source.source_id: source_key},
        expected_generations={pair.source.source_id: pair.source.generation_id},
    )
    bridge = CompanionBridgeMutualTLSRuntime(
        bind_address=forward["core_bind_address"], port=forward["port"],
        tls_context=server_context,
        expected_peer_certificate_sha256=forward["expected_windows_edge_certificate_sha256"],
        receiver=receiver,
        acknowledgment_source_id=pair.acknowledgment.source_id,
        acknowledgment_generation_id=pair.acknowledgment.generation_id,
        acknowledgment_key=acknowledgment_key,
    )
    detector = BridgeForegroundGameDetector(runtime=bridge,
        source_id=pair.source.source_id, generation_id=pair.source.generation_id,
        max_observation_age_seconds=max_observation_age_seconds)
    try:
        output_session = build_wsl_core_avatar_output_session(
            manifest=cfg, session_id=session_id,
            generation_pair_loader=generation_pair_loader,
            bridge_key_reader=bridge_key_reader,
            client_tls_context_factory=client_tls_context_factory,
            generation_receipt_verifier=generation_receipt_verifier,
            admission_receipt_builder=admission_receipt_builder,
            previous_generation_pair=previous_reverse_generation_pair,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        detector.close()
        raise
    return WSLCoreGamingCompanionRuntime(
        foreground_game_detector=detector,
        avatar_output_session=output_session,
        _bridge_runtime=bridge,
    )


__all__ = ["WSLCoreAvatarOutputSession", "WSLCoreGamingCompanionRuntime",
    "build_wsl_core_avatar_output_session", "build_wsl_core_gaming_companion_runtime"]
