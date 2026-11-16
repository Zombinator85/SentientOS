"""Composition of the authority-backed reverse avatar path on the edge.

The factory resolves no secrets itself. Platform custody adapters provide
exact manifest references and already custodied TLS material; authority
callbacks verify generation and command receipts. The owner starts the mTLS
listener before its bounded dispatcher and closes them in reverse order.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Callable, Mapping, Sequence

from .gaming_companion_avatar_output import (
    AvatarCommandDispatchStatus,
    RendererCommandSink,
    WindowsEdgeAvatarCommandDispatchOwner,
)
from .gaming_companion_bridge import CompanionBridgeError, CompanionBridgeReceiver
from .gaming_companion_receipt_replay import AdmissionReceiptReplayGuard
from .gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE, validate_manifest
from .game_performance_bridge import (
    WindowsGamePerformanceBridgePublisher,
    WindowsGamePerformanceObservationPump,
)
from .foreground_game_bridge import (
    WindowsForegroundBridgePublisher, WindowsForegroundObservationPump,
)
from .foreground_game_detection import ForegroundGameDetector
from .windows_game_performance import WindowsGamePerformanceObserver
from .gaming_companion_tls_transport import (
    BridgeGenerationPair,
    CompanionBridgeMutualTLSClient,
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
    game_performance_publisher_configured: bool = False
    game_performance_publisher_running: bool = False
    foreground_game_publisher_configured: bool = False
    foreground_game_publisher_running: bool = False


class WindowsEdgeAvatarRuntime:
    """Own the Windows reverse listener and its receipt-gated state queue."""

    def __init__(self, *, runtime: CompanionBridgeMutualTLSRuntime,
                 dispatcher: WindowsEdgeAvatarCommandDispatchOwner,
                 game_performance_pump: WindowsGamePerformanceObservationPump | None = None,
                 foreground_game_pump: WindowsForegroundObservationPump | None = None,
                 ) -> None:
        self._runtime = runtime
        self._dispatcher = dispatcher
        self._game_performance_pump = game_performance_pump
        self._foreground_game_pump = foreground_game_pump
        self._state = "stopped"
        self._port: int | None = None

    def start(self) -> EdgeAvatarRuntimeStatus:
        if self._state != "stopped":
            raise CompanionBridgeError("edge_avatar_runtime_already_started")
        self._state = "starting"
        try:
            self._port = self._runtime.start()
            self._dispatcher.start()
            if self._game_performance_pump is not None:
                self._game_performance_pump.start()
            if self._foreground_game_pump is not None:
                self._foreground_game_pump.start()
        except Exception:
            try:
                if self._foreground_game_pump is not None:
                    self._foreground_game_pump.close()
            finally:
                try:
                    if self._game_performance_pump is not None:
                        self._game_performance_pump.close()
                finally:
                    try:
                        self._dispatcher.close()
                    finally:
                        self._runtime.close()
                        self._port = None
                        self._state = "failed"
            raise
        self._state = "running"
        return self.status()

    def status(self) -> EdgeAvatarRuntimeStatus:
        return EdgeAvatarRuntimeStatus(self._state, self._port,
            self._dispatcher.status(),
            game_performance_publisher_configured=self._game_performance_pump is not None,
            game_performance_publisher_running=(self._game_performance_pump is not None
                and self._game_performance_pump.status().get("running") is True),
            foreground_game_publisher_configured=self._foreground_game_pump is not None,
            foreground_game_publisher_running=(self._foreground_game_pump is not None
                and self._foreground_game_pump.status().running))

    def close(self) -> EdgeAvatarRuntimeStatus:
        if self._state == "stopped":
            return self.status()
        self._state = "stopping"
        failure: Exception | None = None
        try:
            if self._foreground_game_pump is not None:
                self._foreground_game_pump.close()
        except Exception as exc:
            failure = exc
        try:
            if self._game_performance_pump is not None:
                self._game_performance_pump.close()
        except Exception as exc:
            if failure is None:
                failure = exc
        try:
            self._dispatcher.close()
        except Exception as exc:
            if failure is None:
                failure = exc
        try:
            self._runtime.close()
        except Exception as exc:
            if failure is None:
                failure = exc
        dispatch_status = self._dispatcher.status()
        self._port = None
        self._state = "failed" if failure is not None or dispatch_status.state == "failed" else "stopped"
        if failure is not None:
            raise failure
        return self.status()


def build_windows_edge_avatar_runtime(
    *,
    manifest: Mapping[str, Any],
    generation_pair_loader: GenerationPairLoader,
    bridge_key_reader: BridgeKeyReader,
    server_tls_context_factory: ServerTLSContextFactory,
    generation_receipt_verifier: GenerationReceiptVerifier,
    command_receipt_verifier: CommandReceiptVerifier,
    renderer_sink: RendererCommandSink,
    previous_generation_pair: BridgeGenerationPair | None = None,
    previous_forward_generation_pair: BridgeGenerationPair | None = None,
    client_tls_context_factory: Callable[[str, str, str], Any] | None = None,
    game_process_names: Sequence[str] = (),
    poll_interval_seconds: float = 0.05,
    receipt_replay_guard: AdmissionReceiptReplayGuard | None = None,
) -> WindowsEdgeAvatarRuntime:
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
    game_performance_pump = None
    foreground_game_pump = None
    if game_process_names:
        from .foreground_game_detection import normalize_game_process_names

        if client_tls_context_factory is None:
            raise CompanionBridgeError("edge_game_performance_client_tls_factory_required")
        process_names = normalize_game_process_names(tuple(game_process_names))
        forward = cfg["bridge_tls"]
        forward_pair = generation_pair_loader(
            forward["source_generation_custody_reference"],
            forward["acknowledgment_generation_custody_reference"],
        )
        if type(forward_pair) is not BridgeGenerationPair:
            raise CompanionBridgeError("edge_game_performance_generation_pair_required")
        if forward_pair.source.key_reference != forward["source_key_custody_reference"]:
            raise CompanionBridgeError("edge_game_performance_source_key_reference_mismatch")
        verify_generation_pair_rotation(previous=previous_forward_generation_pair,
            successor=forward_pair, authority_receipt_verifier=generation_receipt_verifier)
        forward_source_key = bridge_key_reader(forward_pair.source.key_reference)
        forward_ack_key = bridge_key_reader(forward_pair.acknowledgment.key_reference)
        if (not isinstance(forward_source_key, bytes) or len(forward_source_key) < 32
                or not isinstance(forward_ack_key, bytes) or len(forward_ack_key) < 32):
            raise CompanionBridgeError("edge_game_performance_bridge_key_unavailable")
        forward_client = CompanionBridgeMutualTLSClient(
            address=forward["core_bind_address"], port=forward["port"],
            server_hostname=forward["server_hostname"],
            tls_context=client_tls_context_factory(
                forward["ca_bundle_reference"],
                forward["windows_edge_client_certificate_reference"],
                forward["windows_edge_client_private_key_reference"]),
            acknowledgment_receiver=CompanionBridgeReceiver(
                source_keys={forward_pair.acknowledgment.source_id: forward_ack_key},
                expected_generations={forward_pair.acknowledgment.source_id:
                    forward_pair.acknowledgment.generation_id}),
            timeout_seconds=2.0)
        publication_lock = threading.Lock()
        sequence = 0

        def allocate_sequence() -> int:
            nonlocal sequence
            sequence += 1
            return sequence

        session_id = "windows-edge-game-observation"
        performance_publisher = WindowsGamePerformanceBridgePublisher(
            observer=WindowsGamePerformanceObserver(), client=forward_client,
            source_id=forward_pair.source.source_id,
            session_id=session_id,
            generation_id=forward_pair.source.generation_id,
            source_key=forward_source_key, process_id=1,
            sequence_allocator=allocate_sequence, publication_lock=publication_lock)
        game_performance_pump = WindowsGamePerformanceObservationPump(
            publisher=performance_publisher, process_names=process_names)
        foreground_publisher = WindowsForegroundBridgePublisher(
            detector=ForegroundGameDetector(), client=forward_client,
            source_id=forward_pair.source.source_id, session_id=session_id,
            generation_id=forward_pair.source.generation_id,
            source_key=forward_source_key, sequence_allocator=allocate_sequence,
            publication_lock=publication_lock)
        foreground_game_pump = WindowsForegroundObservationPump(
            publisher=foreground_publisher, process_names=process_names)
    dispatcher = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=runtime,
        receipt_verifier=command_receipt_verifier,
        renderer_sink=renderer_sink,
        poll_interval_seconds=poll_interval_seconds,
        receipt_replay_guard=receipt_replay_guard,
    )
    return WindowsEdgeAvatarRuntime(runtime=runtime, dispatcher=dispatcher,
        game_performance_pump=game_performance_pump,
        foreground_game_pump=foreground_game_pump)


__all__ = [
    "EdgeAvatarRuntimeStatus", "WindowsEdgeAvatarRuntime",
    "build_windows_edge_avatar_runtime",
]
