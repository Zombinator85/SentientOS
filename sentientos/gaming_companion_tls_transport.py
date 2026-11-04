"""Mutual-TLS transport and protected source-key readers for split-host use.

The existing HMAC envelope remains the application identity/replay layer.
This module adds encrypted, peer-authenticated TCP transport without granting
the process firewall, installation, or host-administration authority.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import ssl
import stat
import threading
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .gaming_companion_bridge import (
    CompanionBridgeError,
    CompanionBridgeReceiver,
    VerifiedBridgeMessage,
    read_frame,
    send_frame,
)
from .gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
    CompanionBridgeTransportError,
    bridge_message_id,
)

MIN_TLS_VERSION = ssl.TLSVersion.TLSv1_2
GENERATION_CUSTODY_SCHEMA = "sentientos.companion_bridge_generation_custody:v1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _read_private_json_record(path: Path | str) -> Mapping[str, Any]:
    target = Path(path)
    try:
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise CompanionBridgeError("bridge_generation_record_unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 16_384
                or (os.name == "posix" and
                    (metadata.st_mode & 0o077 or metadata.st_uid != os.getuid()))):
            raise CompanionBridgeError("bridge_generation_record_custody_invalid")
        chunks = bytearray()
        while len(chunks) <= 16_384:
            block = os.read(descriptor, min(4096, 16_385 - len(chunks)))
            if not block:
                break
            chunks.extend(block)
        if len(chunks) > 16_384:
            raise CompanionBridgeError("bridge_generation_record_custody_invalid")
        value = json.loads(chunks.decode("utf-8"))
    except CompanionBridgeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompanionBridgeError("bridge_generation_record_unavailable") from exc
    finally:
        os.close(descriptor)
    if not isinstance(value, Mapping):
        raise CompanionBridgeError("bridge_generation_record_shape_invalid")
    return value


@dataclass(frozen=True, slots=True)
class BridgeGenerationCustodyRecord:
    source_id: str
    generation_id: str
    key_reference: str
    issuer_id: str
    issued_at: str
    authority_receipt_digest: str
    predecessor_generation_id: str | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BridgeGenerationCustodyRecord":
        fields = {"schema_version", "source_id", "generation_id", "key_reference",
                  "issuer_id", "issued_at", "authority_receipt_digest",
                  "predecessor_generation_id"}
        if not isinstance(value, Mapping) or set(value) != fields or value.get("schema_version") != GENERATION_CUSTODY_SCHEMA:
            raise CompanionBridgeError("bridge_generation_record_shape_invalid")
        for name in ("source_id", "generation_id", "issuer_id"):
            if not isinstance(value[name], str) or _IDENTIFIER.fullmatch(value[name]) is None:
                raise CompanionBridgeError("bridge_generation_record_identity_invalid")
        key_ref = value["key_reference"]
        if not isinstance(key_ref, str) or not key_ref.strip() or len(key_ref) > 512:
            raise CompanionBridgeError("bridge_generation_key_reference_invalid")
        receipt_digest = value["authority_receipt_digest"]
        if not isinstance(receipt_digest, str) or _DIGEST.fullmatch(receipt_digest) is None:
            raise CompanionBridgeError("bridge_generation_authority_receipt_invalid")
        predecessor = value["predecessor_generation_id"]
        if predecessor is not None and (not isinstance(predecessor, str)
                or _IDENTIFIER.fullmatch(predecessor) is None):
            raise CompanionBridgeError("bridge_generation_predecessor_invalid")
        stamp = value["issued_at"]
        if not isinstance(stamp, str):
            raise CompanionBridgeError("bridge_generation_timestamp_invalid")
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CompanionBridgeError("bridge_generation_timestamp_invalid") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise CompanionBridgeError("bridge_generation_timestamp_invalid")
        return cls(value["source_id"], value["generation_id"], key_ref,
                   value["issuer_id"], stamp, receipt_digest, predecessor)

    @classmethod
    def load(cls, path: Path | str) -> "BridgeGenerationCustodyRecord":
        return cls.from_mapping(_read_private_json_record(path))

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": GENERATION_CUSTODY_SCHEMA, **asdict(self)}


@dataclass(frozen=True, slots=True)
class BridgeGenerationPair:
    """Independently custodied sender and acknowledgment generations."""

    source: BridgeGenerationCustodyRecord
    acknowledgment: BridgeGenerationCustodyRecord

    def __post_init__(self) -> None:
        if (type(self.source) is not BridgeGenerationCustodyRecord
                or type(self.acknowledgment) is not BridgeGenerationCustodyRecord):
            raise CompanionBridgeError("bridge_generation_pair_record_invalid")
        if (self.source.source_id == self.acknowledgment.source_id
                or self.source.generation_id == self.acknowledgment.generation_id
                or self.source.key_reference == self.acknowledgment.key_reference
                or self.source.authority_receipt_digest == self.acknowledgment.authority_receipt_digest):
            raise CompanionBridgeError("bridge_generation_pair_identity_collision")

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": "sentientos.companion_bridge_generation_pair:v1",
                "source": self.source.to_dict(),
                "acknowledgment": self.acknowledgment.to_dict()}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BridgeGenerationPair":
        if (not isinstance(value, Mapping)
                or set(value) != {"schema_version", "source", "acknowledgment"}
                or value.get("schema_version") != "sentientos.companion_bridge_generation_pair:v1"
                or not isinstance(value.get("source"), Mapping)
                or not isinstance(value.get("acknowledgment"), Mapping)):
            raise CompanionBridgeError("bridge_generation_pair_shape_invalid")
        return cls(BridgeGenerationCustodyRecord.from_mapping(value["source"]),
                   BridgeGenerationCustodyRecord.from_mapping(value["acknowledgment"]))

    @classmethod
    def load(cls, path: Path | str) -> "BridgeGenerationPair":
        return cls.from_mapping(_read_private_json_record(path))


def verify_generation_rotation(*, previous: BridgeGenerationCustodyRecord | None,
                               successor: BridgeGenerationCustodyRecord,
                               authority_receipt_verifier: Callable[[str, BridgeGenerationCustodyRecord], bool]) -> None:
    """Require a separately verified authority receipt before accepting rotation."""
    if not callable(authority_receipt_verifier):
        raise CompanionBridgeError("bridge_generation_authority_verifier_required")
    if previous is None:
        if successor.predecessor_generation_id is not None:
            raise CompanionBridgeError("bridge_initial_generation_predecessor_invalid")
    else:
        previous_time = datetime.fromisoformat(previous.issued_at.replace("Z", "+00:00"))
        successor_time = datetime.fromisoformat(successor.issued_at.replace("Z", "+00:00"))
        if (successor.source_id != previous.source_id
                or successor.generation_id == previous.generation_id
                or successor.predecessor_generation_id != previous.generation_id
                or successor.key_reference == previous.key_reference
                or successor_time <= previous_time):
            raise CompanionBridgeError("bridge_generation_rotation_chain_invalid")
    try:
        verified = authority_receipt_verifier(successor.authority_receipt_digest, successor)
    except Exception as exc:
        raise CompanionBridgeError("bridge_generation_authority_receipt_invalid") from exc
    if verified is not True:
        raise CompanionBridgeError("bridge_generation_authority_receipt_unverified")


def verify_generation_pair_rotation(*, previous: BridgeGenerationPair | None,
                                    successor: BridgeGenerationPair,
                                    authority_receipt_verifier: Callable[[str, BridgeGenerationCustodyRecord], bool]) -> None:
    """Verify both endpoint generations and their independent predecessor chains."""
    if type(successor) is not BridgeGenerationPair:
        raise CompanionBridgeError("bridge_generation_pair_record_invalid")
    verify_generation_rotation(
        previous=previous.source if previous is not None else None,
        successor=successor.source,
        authority_receipt_verifier=authority_receipt_verifier,
    )
    verify_generation_rotation(
        previous=previous.acknowledgment if previous is not None else None,
        successor=successor.acknowledgment,
        authority_receipt_verifier=authority_receipt_verifier,
    )


def _validate_private_address(address: str) -> tuple[str, int]:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise CompanionBridgeError("bridge_private_address_invalid") from exc
    if parsed.is_unspecified or parsed.is_multicast or parsed.is_link_local:
        raise CompanionBridgeError("bridge_private_address_not_routable")
    if not (parsed.is_private or parsed.is_loopback) or parsed.is_global:
        raise CompanionBridgeError("bridge_private_address_required")
    return str(parsed), socket.AF_INET6 if parsed.version == 6 else socket.AF_INET


def read_posix_bridge_source_key(path: Path | str) -> bytes:
    """Read an operator-provisioned key from a private, non-symlink POSIX file."""
    target = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CompanionBridgeError("bridge_source_key_custody_invalid") from exc
        raise CompanionBridgeError("bridge_source_key_unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077
                or metadata.st_uid != os.getuid() or metadata.st_size < 32
                or metadata.st_size > 128):
            raise CompanionBridgeError("bridge_source_key_custody_invalid")
        key = os.read(descriptor, 129)
        if len(key) < 32 or len(key) > 128:
            raise CompanionBridgeError("bridge_source_key_custody_invalid")
        return key
    finally:
        os.close(descriptor)


def read_windows_dpapi_bridge_source_key(path: Path | str) -> bytes:
    """Unseal a DPAPI CurrentUser key file into memory on Windows only."""
    if os.name != "nt":
        raise CompanionBridgeError("windows_dpapi_unavailable_on_platform")
    try:
        ciphertext = Path(path).read_bytes()
    except OSError as exc:
        raise CompanionBridgeError("bridge_source_key_unavailable") from exc
    if not 1 <= len(ciphertext) <= 4096:
        raise CompanionBridgeError("bridge_source_key_custody_invalid")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    source_buffer = (ctypes.c_ubyte * len(ciphertext)).from_buffer_copy(ciphertext)
    source = DataBlob(len(ciphertext), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    crypt32.CryptUnprotectData.argtypes = (
        ctypes.POINTER(DataBlob), ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(DataBlob))
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0x1,
                                      ctypes.byref(destination)):
        raise CompanionBridgeError("windows_dpapi_unseal_failed")
    try:
        key = ctypes.string_at(destination.pbData, destination.cbData)
        if not 32 <= len(key) <= 128:
            raise CompanionBridgeError("bridge_source_key_custody_invalid")
        return key
    finally:
        ctypes.memset(destination.pbData, 0, destination.cbData)
        kernel32.LocalFree(destination.pbData)


def _server_context_is_protected(context: ssl.SSLContext) -> bool:
    return (isinstance(context, ssl.SSLContext)
            and context.verify_mode == ssl.CERT_REQUIRED
            and context.minimum_version >= MIN_TLS_VERSION)


def _client_context_is_protected(context: ssl.SSLContext) -> bool:
    return (_server_context_is_protected(context) and context.check_hostname)


class CompanionBridgeMutualTLSRuntime(CompanionBridgeLoopbackRuntime):
    """Bounded TLS listener bound to one exact private or loopback address."""

    def __init__(self, *, bind_address: str, tls_context: ssl.SSLContext,
                 expected_peer_certificate_sha256: str,
                 receiver: CompanionBridgeReceiver, acknowledgment_source_id: str,
                 acknowledgment_generation_id: str, acknowledgment_key: bytes,
                 port: int = 0, queue_capacity: int = 16,
                 socket_timeout_seconds: float = 1.0, clock: Any = None) -> None:
        address, family = _validate_private_address(bind_address)
        if not _server_context_is_protected(tls_context):
            raise CompanionBridgeError("bridge_server_mutual_tls_required")
        if not isinstance(expected_peer_certificate_sha256, str) or _DIGEST.fullmatch(expected_peer_certificate_sha256) is None:
            raise CompanionBridgeError("bridge_peer_certificate_pin_required")
        super().__init__(receiver=receiver, acknowledgment_source_id=acknowledgment_source_id,
            acknowledgment_generation_id=acknowledgment_generation_id,
            acknowledgment_key=acknowledgment_key, port=port,
            queue_capacity=queue_capacity, socket_timeout_seconds=socket_timeout_seconds,
            clock=clock)
        self._bind_address = address
        self._socket_family = family
        self._tls_context = tls_context
        self._expected_peer_certificate_sha256 = expected_peer_certificate_sha256

    def supervisor_identity_bindings(self) -> tuple[dict[str, str], str, str]:
        """Return non-secret identities bound to this listener and receiver."""
        return (dict(self._receiver.expected_generations), self._ack_source_id,
                self._ack_generation_id)

    def start(self) -> int:
        with self._lock:
            if self._thread is not None or self._started_once:
                raise CompanionBridgeError("bridge_runtime_generation_rotation_required")
            listener = socket.socket(self._socket_family, socket.SOCK_STREAM)
            listener.settimeout(0.2)
            try:
                listener.bind((self._bind_address, self._requested_port))
                listener.listen(8)
            except OSError:
                listener.close()
                raise
            self._listener = listener
            self._started_once = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._serve_tls,
                name="sentientos-companion-mtls-bridge", daemon=True)
            self._thread.start()
            return int(listener.getsockname()[1])

    def close(self) -> None:
        with self._lock:
            listener, thread = self._listener, self._thread
            self._stop.set()
        if listener is None:
            return
        try:
            with socket.create_connection((self._bind_address,
                    int(listener.getsockname()[1])), timeout=0.25):
                pass
        except OSError:
            pass
        listener.close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self._socket_timeout + 0.5))
        with self._lock:
            self._listener = None
            self._thread = None

    def _serve_tls(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while not self._stop.is_set():
            try:
                raw_connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self._stop.is_set():
                    with self._lock:
                        self._rejected += 1
                break
            raw_connection.settimeout(self._socket_timeout)
            try:
                connection = self._tls_context.wrap_socket(raw_connection, server_side=True)
            except (OSError, ssl.SSLError):
                raw_connection.close()
                with self._lock:
                    self._rejected += 1
                continue
            peer_certificate = connection.getpeercert(binary_form=True)
            peer_digest = hashlib.sha256(peer_certificate).hexdigest() if peer_certificate else ""
            if not hmac.compare_digest(peer_digest, self._expected_peer_certificate_sha256):
                connection.close()
                with self._lock:
                    self._rejected += 1
                continue
            with connection:
                if self._messages.full():
                    with self._lock:
                        self._rejected += 1
                    try:
                        connection.settimeout(self._socket_timeout)
                        encoded = read_frame(connection)
                        send_frame(connection, self._backpressure_ack(encoded))
                    except (CompanionBridgeError, OSError):
                        with self._lock:
                            self._acknowledgment_failures += 1
                    continue
                try:
                    connection.settimeout(self._socket_timeout)
                    encoded = read_frame(connection)
                    message = self._receiver.accept(encoded)
                    try:
                        self._messages.put_nowait(message)
                    except Exception:
                        send_frame(connection, self._backpressure_ack(encoded))
                        with self._lock:
                            self._rejected += 1
                        continue
                    with self._lock:
                        self._accepted += 1
                    try:
                        send_frame(connection, self._ack(message))
                    except (CompanionBridgeError, OSError):
                        with self._lock:
                            self._acknowledgment_failures += 1
                except (CompanionBridgeError, OSError):
                    with self._lock:
                        self._rejected += 1


class CompanionBridgeMutualTLSClient(CompanionBridgeLoopbackClient):
    """One-message TLS client; uncertain deliveries are returned, never replayed."""

    def __init__(self, *, address: str, port: int, server_hostname: str,
                 tls_context: ssl.SSLContext,
                 acknowledgment_receiver: CompanionBridgeReceiver,
                 expected_server_certificate_sha256: str | None = None,
                 timeout_seconds: float = 2.0) -> None:
        self._address, self._family = _validate_private_address(address)
        if type(port) is not int or not 1 <= port <= 65535:
            raise CompanionBridgeError("bridge_tcp_port_invalid")
        if not isinstance(server_hostname, str) or not server_hostname or len(server_hostname) > 253:
            raise CompanionBridgeError("bridge_tls_server_name_invalid")
        if not _client_context_is_protected(tls_context):
            raise CompanionBridgeError("bridge_client_mutual_tls_required")
        if not isinstance(acknowledgment_receiver, CompanionBridgeReceiver):
            raise CompanionBridgeError("bridge_acknowledgment_receiver_required")
        if (expected_server_certificate_sha256 is not None
                and (not isinstance(expected_server_certificate_sha256, str)
                     or _DIGEST.fullmatch(expected_server_certificate_sha256) is None)):
            raise CompanionBridgeError("bridge_tls_server_certificate_pin_invalid")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or timeout_seconds <= 0 or timeout_seconds > 30):
            raise CompanionBridgeError("bridge_socket_timeout_invalid")
        super().__init__(port=port, acknowledgment_receiver=acknowledgment_receiver,
                         timeout_seconds=float(timeout_seconds))
        self._port = port
        self._server_hostname = server_hostname
        self._context = tls_context
        self._ack_receiver = acknowledgment_receiver
        self._expected_server_certificate_sha256 = expected_server_certificate_sha256
        self._timeout = float(timeout_seconds)

    def send(self, encoded: bytes) -> VerifiedBridgeMessage:
        expected_message_id = bridge_message_id(encoded)
        raw: socket.socket | None = None
        try:
            raw = socket.socket(self._family, socket.SOCK_STREAM)
            raw.settimeout(self._timeout)
            raw.connect((self._address, self._port))
        except OSError as exc:
            if raw is not None:
                raw.close()
            raise CompanionBridgeTransportError("bridge_tls_connection_unavailable",
                delivery_state="not_sent", failure_phase="tcp_connect",
                failure_type=type(exc).__name__, failure_errno=exc.errno) from exc
        try:
            connection = self._context.wrap_socket(raw, server_hostname=self._server_hostname)
        except (OSError, ssl.SSLError) as exc:
            raw.close()
            raise CompanionBridgeTransportError("bridge_tls_connection_unavailable",
                delivery_state="not_sent", failure_phase="tls_handshake",
                failure_type=type(exc).__name__, failure_errno=exc.errno) from exc
        if self._expected_server_certificate_sha256 is not None:
            peer_certificate = connection.getpeercert(binary_form=True)
            observed_pin = hashlib.sha256(peer_certificate).hexdigest() if peer_certificate else ""
            if not hmac.compare_digest(observed_pin,
                    self._expected_server_certificate_sha256):
                connection.close()
                raise CompanionBridgeTransportError(
                    "bridge_tls_server_certificate_pin_mismatch", delivery_state="not_sent")
        try:
            with connection:
                try:
                    send_frame(connection, encoded)
                    acknowledgment_bytes = read_frame(connection)
                except (OSError, CompanionBridgeError) as exc:
                    raise CompanionBridgeTransportError("bridge_delivery_indeterminate",
                        delivery_state="indeterminate") from exc
        except CompanionBridgeTransportError:
            raise
        try:
            acknowledgment = self._ack_receiver.accept(acknowledgment_bytes)
        except CompanionBridgeError as exc:
            raise CompanionBridgeTransportError("bridge_acknowledgment_invalid",
                delivery_state="indeterminate") from exc
        if (acknowledgment.kind != "acknowledgment"
                or acknowledgment.payload.get("message_id") != expected_message_id):
            raise CompanionBridgeTransportError("bridge_acknowledgment_mismatch",
                delivery_state="indeterminate")
        if acknowledgment.payload.get("disposition") == "rejected_backpressure":
            raise CompanionBridgeTransportError("bridge_backpressure_rejected",
                delivery_state="not_accepted")
        if acknowledgment.payload.get("disposition") != "accepted":
            raise CompanionBridgeTransportError("bridge_acknowledgment_disposition_invalid",
                delivery_state="indeterminate")
        return acknowledgment


__all__ = ["CompanionBridgeMutualTLSRuntime", "CompanionBridgeMutualTLSClient",
           "BridgeGenerationCustodyRecord", "BridgeGenerationPair",
           "verify_generation_rotation", "verify_generation_pair_rotation",
           "read_posix_bridge_source_key", "read_windows_dpapi_bridge_source_key"]
