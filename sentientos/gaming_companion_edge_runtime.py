"""Composition of the authority-backed reverse avatar path on the edge.

The factory resolves no secrets itself. Platform custody adapters provide
exact manifest references and already custodied TLS material; authority
callbacks verify generation and command receipts. The owner starts the mTLS
listener before its bounded dispatcher and closes them in reverse order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .gaming_companion_avatar_output import (
    AvatarCommandDispatchStatus,
    RendererCommandSink,
    WindowsEdgeAvatarCommandDispatchOwner,
)
from .gaming_companion_bridge import CompanionBridgeError, CompanionBridgeReceiver
from .gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE, validate_manifest
from .gaming_companion_tls_transport import (
    BridgeGenerationPair,
    CompanionBridgeMutualTLSRuntime,
    verify_generation_pair_rotation,
)


GenerationPairLoader = Callable[[str, str], BridgeGenerationPair]
BridgeKeyReader = Callable[[str], bytes]
ServerTLSContextFactory = Callable[[str, str, str], Any]
GenerationReceiptVerifier = Callable[[str, object], bool]
CommandReceiptVerifier = Callable[[str, str, object], bool]


@dataclass(frozen=True, slots=True)
class EdgeAvatarRuntimeStatus:
    state: str
    listener_port: int | None
    dispatch: AvatarCommandDispatchStatus
    authority_effects_performed: bool = False
    renderer_effect_proven: bool = False


class WindowsEdgeAvatarRuntime:
    """Own the Windows reverse listener and its receipt-gated state queue."""

    def __init__(self, *, runtime: CompanionBridgeMutualTLSRuntime,
                 dispatcher: WindowsEdgeAvatarCommandDispatchOwner) -> None:
        self._runtime = runtime
        self._dispatcher = dispatcher
        self._state = "stopped"
        self._port: int | None = None

    def start(self) -> EdgeAvatarRuntimeStatus:
        if self._state != "stopped":
            raise CompanionBridgeError("edge_avatar_runtime_already_started")
        self._state = "starting"
        try:
            self._port = self._runtime.start()
            self._dispatcher.start()
        except Exception:
            self._dispatcher.close()
            self._runtime.close()
            self._port = None
            self._state = "failed"
            raise
        self._state = "running"
        return self.status()

    def status(self) -> EdgeAvatarRuntimeStatus:
        return EdgeAvatarRuntimeStatus(self._state, self._port,
            self._dispatcher.status())

    def close(self) -> EdgeAvatarRuntimeStatus:
        if self._state == "stopped":
            return self.status()
        self._state = "stopping"
        try:
            self._dispatcher.close()
        finally:
            self._runtime.close()
        dispatch_status = self._dispatcher.status()
        self._port = None
        self._state = "failed" if dispatch_status.state == "failed" else "stopped"
        return self.status()


def build_windows_edge_avatar_runtime(*, manifest: Mapping[str, Any],
        generation_pair_loader: GenerationPairLoader,
        bridge_key_reader: BridgeKeyReader,
        server_tls_context_factory: ServerTLSContextFactory,
        generation_receipt_verifier: GenerationReceiptVerifier,
        command_receipt_verifier: CommandReceiptVerifier,
        renderer_sink: RendererCommandSink,
        previous_generation_pair: BridgeGenerationPair | None = None,
        poll_interval_seconds: float = 0.05) -> WindowsEdgeAvatarRuntime:
    """Build, but do not start, the v3 Windows edge reverse-avatar runtime.

    Each resolver is called with the exact opaque reference from the manifest
    or its authority-issued generation record. No secret or certificate is
    created, copied, logged, or persisted here.
    """
    cfg = validate_manifest(manifest)
    if cfg["schema_version"] != SCHEMA_MUTUAL_TLS_REVERSE:
        raise CompanionBridgeError("edge_avatar_reverse_manifest_v3_required")
    reverse = cfg["reverse_avatar_tls"]
    pair = generation_pair_loader(
        reverse["source_generation_custody_reference"],
        reverse["acknowledgment_generation_custody_reference"],
    )
    if type(pair) is not BridgeGenerationPair:
        raise CompanionBridgeError("edge_avatar_generation_pair_required")
    if pair.source.key_reference != reverse["source_key_custody_reference"]:
        raise CompanionBridgeError("edge_avatar_source_key_reference_mismatch")
    verify_generation_pair_rotation(previous=previous_generation_pair,
        successor=pair, authority_receipt_verifier=generation_receipt_verifier)
    source_key = bridge_key_reader(pair.source.key_reference)
    acknowledgment_key = bridge_key_reader(pair.acknowledgment.key_reference)
    if (not isinstance(source_key, bytes) or not isinstance(acknowledgment_key, bytes)
            or len(source_key) < 32 or len(acknowledgment_key) < 32):
        raise CompanionBridgeError("edge_avatar_bridge_key_unavailable")
    tls_context = server_tls_context_factory(
        reverse["ca_bundle_reference"],
        reverse["windows_edge_certificate_reference"],
        reverse["windows_edge_private_key_reference"],
    )
    receiver = CompanionBridgeReceiver(
        source_keys={pair.source.source_id: source_key},
        expected_generations={pair.source.source_id: pair.source.generation_id},
    )
    runtime = CompanionBridgeMutualTLSRuntime(
        bind_address=reverse["windows_bind_address"],
        port=reverse["port"],
        tls_context=tls_context,
        expected_peer_certificate_sha256=reverse["expected_wsl_core_certificate_sha256"],
        receiver=receiver,
        acknowledgment_source_id=pair.acknowledgment.source_id,
        acknowledgment_generation_id=pair.acknowledgment.generation_id,
        acknowledgment_key=acknowledgment_key,
    )
    dispatcher = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=runtime,
        receipt_verifier=command_receipt_verifier,
        renderer_sink=renderer_sink,
        poll_interval_seconds=poll_interval_seconds,
    )
    return WindowsEdgeAvatarRuntime(runtime=runtime, dispatcher=dispatcher)


__all__ = [
    "EdgeAvatarRuntimeStatus", "WindowsEdgeAvatarRuntime",
    "build_windows_edge_avatar_runtime",
]
