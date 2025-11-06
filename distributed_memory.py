"""Distributed memory synchronisation across SentientOS nodes."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import socket
import threading
import time
from collections import deque
from datetime import datetime, timezone
from itertools import count
from typing import Deque, Dict, Mapping, Optional

import requests
from dotenv import load_dotenv

import memory_manager as mm
from logging_config import get_log_path
from node_registry import NODE_TOKEN, registry
from sentientos.daemons import pulse_bus

try:  # pragma: no cover - optional dependency
    import zstandard as zstd
except Exception:  # pragma: no cover - optional dependency
    zstd = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _NativeAESGCM
except Exception:  # pragma: no cover - optional dependency
    _NativeAESGCM = None  # type: ignore

load_dotenv()

LOGGER = logging.getLogger(__name__)

_SYNC_INTERVAL_SECONDS = float(os.getenv("SENTIENTOS_MEMORY_SYNC_INTERVAL", "30"))
_REMOTE_TIMEOUT = 8.0
_HEADER_TOKEN = "X-Node-Token"
_MEMORY_ENDPOINT = "/memory/export"
_COMPRESSED_ENCODING = "base64+zstd"
_REFLECTION_ENDPOINT = "/reflect/sync"
_REFLECTION_SCHEMA_VERSION = 1
_RECENT_REFLECTION_CACHE = 64


class _ReflectionCipher:
    """Symmetric authenticated encryption for reflection payloads."""

    _TAG_LEN = 16

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("Reflection sync key must be 32 bytes")
        self._key = key
        self._aes = _NativeAESGCM(key) if _NativeAESGCM is not None else None

    def encrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
        if self._aes is not None:
            return self._aes.encrypt(nonce, data, associated_data)
        return self._fallback_encrypt(nonce, data, associated_data)

    def decrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
        if self._aes is not None:
            return self._aes.decrypt(nonce, data, associated_data)
        return self._fallback_decrypt(nonce, data, associated_data)

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        stream = bytearray()
        for counter in count():
            if len(stream) >= length:
                break
            block = hashlib.sha256(self._key + nonce + counter.to_bytes(4, "big")).digest()
            stream.extend(block)
        return bytes(stream[:length])

    def _fallback_encrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
        ciphertext = bytes(a ^ b for a, b in zip(data, self._keystream(nonce, len(data))))
        tag = hmac.new(self._key, (associated_data or b"") + ciphertext, hashlib.sha256).digest()
        return ciphertext + tag[: self._TAG_LEN]

    def _fallback_decrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
        if len(data) < self._TAG_LEN:
            raise ValueError("ciphertext too short")
        ciphertext = data[:-self._TAG_LEN]
        tag = data[-self._TAG_LEN:]
        expected = hmac.new(self._key, (associated_data or b"") + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(expected[: self._TAG_LEN], tag):
            raise ValueError("authentication failed")
        return bytes(a ^ b for a, b in zip(ciphertext, self._keystream(nonce, len(ciphertext))))


def _derive_sync_key() -> Optional[bytes]:
    explicit = os.getenv("SENTIENTOS_REFLECTION_KEY", "").strip()
    if explicit:
        try:
            raw = base64.b64decode(explicit)
        except (binascii.Error, ValueError):
            raw = hashlib.sha256(explicit.encode("utf-8")).digest()
        else:
            if len(raw) != 32:
                raw = hashlib.sha256(raw).digest()
        return raw
    token = str(NODE_TOKEN or os.getenv("NODE_TOKEN", "")).strip()
    if not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).digest()


def _parse_timestamp(timestamp: str) -> float:
    try:
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp).timestamp()
    except Exception:
        return 0.0


def encode_payload(payload: Dict[str, object], *, allow_compression: bool = False) -> tuple[bytes, Dict[str, str]]:
    """Return a payload ready for HTTP transmission.

    When ``allow_compression`` is true and :mod:`zstandard` is available the
    payload is compressed and base64 encoded to keep transport simple.
    """

    raw = json.dumps(payload).encode("utf-8")
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if allow_compression and zstd:
        compressor = zstd.ZstdCompressor()
        compressed = compressor.compress(raw)
        headers["Content-Encoding"] = _COMPRESSED_ENCODING
        return base64.b64encode(compressed), headers
    return raw, headers


def _decompress_payload(data: bytes, encoding: str | None) -> Dict[str, object]:
    if not encoding:
        return json.loads(data.decode("utf-8"))
    if encoding == _COMPRESSED_ENCODING and zstd:
        decoded = base64.b64decode(data)
        decompressor = zstd.ZstdDecompressor()
        restored = decompressor.decompress(decoded)
        return json.loads(restored.decode("utf-8"))
    return json.loads(data.decode("utf-8"))


def _local_fragments() -> Dict[str, dict]:
    fragments: Dict[str, dict] = {}
    for fragment in mm.iter_fragments(reverse=False):
        fragment_id = fragment.get("id")
        if fragment_id:
            fragments[str(fragment_id)] = fragment
    return fragments


def _write_fragment(fragment: dict) -> None:
    fragment_id = fragment.get("id")
    if not fragment_id:
        return
    path = mm._fragment_path(fragment_id)  # type: ignore[attr-defined]
    try:
        path.write_text(json.dumps(fragment, ensure_ascii=False), encoding="utf-8")
    except OSError:
        LOGGER.debug("Failed to write synchronised fragment %s", fragment_id, exc_info=True)


class DistributedMemorySynchronizer:
    """Periodically reconcile memory fragments with neighbouring nodes."""

    def __init__(self, interval_seconds: float = _SYNC_INTERVAL_SECONDS) -> None:
        self._interval = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._reflection_log = get_log_path("federated_reflections.jsonl")
        self._reflection_log.parent.mkdir(parents=True, exist_ok=True)
        self._recent_reflections: Deque[str] = deque(maxlen=_RECENT_REFLECTION_CACHE)
        self._pulse_subscription = None
        self._cipher: _ReflectionCipher | None = None
        self._cipher_key: bytes | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not (NODE_TOKEN or os.getenv("SENTIENTOS_REFLECTION_KEY")):
            LOGGER.warning("Memory federation requires NODE_TOKEN or SENTIENTOS_REFLECTION_KEY; skipping start.")
            return
        self._subscribe_to_reflections()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        banner = f"[SentientOS] Memory federation enabled (interval = {int(self._interval)} s)"
        LOGGER.info(banner)
        print(banner)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if self._pulse_subscription and getattr(self._pulse_subscription, "active", False):
            try:
                self._pulse_subscription.unsubscribe()
            except Exception:  # pragma: no cover - defensive cleanup
                LOGGER.debug("Failed to unsubscribe pulse listener", exc_info=True)
        self._pulse_subscription = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._sync_once()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Memory synchronisation step failed: %s", exc, exc_info=True)
            self._stop.wait(self._interval)

    def _subscribe_to_reflections(self) -> None:
        if self._pulse_subscription is not None:
            return
        try:
            self._pulse_subscription = pulse_bus.subscribe(self._handle_pulse_event)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Unable to subscribe to pulse bus for reflection sync", exc_info=True)
            self._pulse_subscription = None

    def _handle_pulse_event(self, event: Mapping[str, object]) -> None:
        if not isinstance(event, Mapping):
            return
        if str(event.get("event_type") or "") != "architect_reflection_complete":
            return
        source_peer = str(event.get("source_peer") or "local")
        if source_peer not in {"", "local"}:
            return
        summary = self._compact_reflection(event)
        if not summary:
            return
        summary_id = str(summary.get("summary_id") or "").strip()
        if summary_id and not self._remember_reflection(summary_id):
            return
        self._broadcast_reflection(summary)

    def _compact_reflection(self, event: Mapping[str, object]) -> Optional[Dict[str, object]]:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            return None
        summary_text = str(payload.get("summary") or "").strip()
        if not summary_text:
            return None
        summary_text = summary_text[:320]
        cycle_raw = payload.get("cycle")
        try:
            cycle_number = int(cycle_raw)
        except (TypeError, ValueError):
            cycle_number = 0
        file_ref = str(payload.get("file") or "").strip()
        summary_id = file_ref or (f"cycle-{cycle_number}" if cycle_number else "")
        origin = registry.local_hostname or socket.gethostname()
        timestamp = str(event.get("timestamp") or datetime.utcnow().replace(tzinfo=timezone.utc).isoformat())
        next_priorities: list[dict[str, object]] = []
        next_raw = payload.get("next_priorities") or []
        if isinstance(next_raw, list):
            for entry in next_raw:
                if isinstance(entry, Mapping):
                    text = str(entry.get("text") or "").strip()
                    if len(text) > 120:
                        text = text[:117].rstrip() + "…"
                    next_priorities.append(
                        {
                            "id": entry.get("id"),
                            "text": text,
                            "status": entry.get("status"),
                        }
                    )
                elif isinstance(entry, str):
                    text = entry.strip()
                    if text:
                        next_priorities.append({"text": text[:120]})
                if len(next_priorities) >= 4:
                    break
        successes = payload.get("successes")
        failures = payload.get("failures")
        regressions = payload.get("regressions")
        summary = {
            "summary_id": summary_id or (f"cycle-{cycle_number}" if cycle_number else ""),
            "cycle": cycle_number,
            "summary": summary_text,
            "timestamp": timestamp,
            "next_priorities": next_priorities,
            "successes": len(successes) if isinstance(successes, list) else 0,
            "failures": len(failures) if isinstance(failures, list) else 0,
            "regressions": len(regressions) if isinstance(regressions, list) else 0,
            "origin": origin,
            "source_peer": source_peer or "local",
        }
        return summary

    def _remember_reflection(self, summary_id: str) -> bool:
        token = summary_id.strip()
        if not token:
            return True
        if token in self._recent_reflections:
            return False
        self._recent_reflections.append(token)
        return True

    def _get_cipher(self) -> Optional[_ReflectionCipher]:
        key = _derive_sync_key()
        if key is None:
            return None
        if self._cipher is None or self._cipher_key != key:
            try:
                self._cipher = _ReflectionCipher(key)
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Failed to initialise reflection cipher", exc_info=True)
                self._cipher = None
                self._cipher_key = None
                return None
            self._cipher_key = key
        return self._cipher

    def _encode_reflection_summary(self, summary: Mapping[str, object]) -> Optional[Dict[str, object]]:
        cipher = self._get_cipher()
        if cipher is None:
            LOGGER.debug("Reflection cipher unavailable; skipping broadcast")
            return None
        nonce = os.urandom(12)
        payload = dict(summary)
        payload.setdefault("schema", _REFLECTION_SCHEMA_VERSION)
        plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        digest = hashlib.sha256(plaintext).hexdigest()
        sender = summary.get("origin") or registry.local_hostname or socket.gethostname()
        return {
            "schema": _REFLECTION_SCHEMA_VERSION,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "sender": sender,
            "digest": digest,
        }

    def _broadcast_reflection(self, summary: Mapping[str, object]) -> None:
        packet = self._encode_reflection_summary(summary)
        if packet is None:
            return
        nodes = list(registry.iter_remote_nodes(trusted_only=True))
        if not nodes:
            return
        headers = {_HEADER_TOKEN: NODE_TOKEN} if NODE_TOKEN else {}
        for node in nodes:
            url = f"http://{node.ip}:{node.port}{_REFLECTION_ENDPOINT}"
            try:
                response = requests.post(url, json=packet, headers=headers, timeout=_REMOTE_TIMEOUT)
            except requests.RequestException as exc:  # pragma: no cover - defensive
                LOGGER.debug("Reflection sync to %s failed: %s", node.hostname, exc)
                continue
            if response.status_code != 200:
                LOGGER.debug("Reflection sync to %s returned %s", node.hostname, response.status_code)

    def _log_reflection(self, summary: Mapping[str, object]) -> None:
        try:
            with self._reflection_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(summary, ensure_ascii=False) + "\n")
        except OSError:  # pragma: no cover - defensive
            LOGGER.debug("Failed to persist federated reflection", exc_info=True)

    def _publish_reflection_event(self, summary: Mapping[str, object]) -> None:
        event = {
            "timestamp": summary.get("timestamp") or datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "source_daemon": "DistributedMemorySynchronizer",
            "event_type": "federated_reflection_received",
            "priority": "info",
            "payload": dict(summary),
        }
        try:
            pulse_bus.publish(event)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Failed to publish federated reflection event", exc_info=True)

    def receive_reflection(self, payload: Mapping[str, object], *, source: str | None = None) -> Dict[str, object]:
        cipher = self._get_cipher()
        if cipher is None:
            return {"accepted": False, "reason": "cipher_unavailable"}
        nonce_b64 = payload.get("nonce")
        ciphertext_b64 = payload.get("ciphertext")
        if not isinstance(nonce_b64, str) or not isinstance(ciphertext_b64, str):
            return {"accepted": False, "reason": "invalid_payload"}
        try:
            nonce = base64.b64decode(nonce_b64)
            ciphertext = base64.b64decode(ciphertext_b64)
        except (binascii.Error, ValueError):
            return {"accepted": False, "reason": "invalid_encoding"}
        digest = str(payload.get("digest") or "")
        try:
            plaintext = cipher.decrypt(nonce, ciphertext, None)
        except Exception:
            return {"accepted": False, "reason": "decrypt_failed"}
        if digest:
            computed = hashlib.sha256(plaintext).hexdigest()
            if digest != computed:
                return {"accepted": False, "reason": "digest_mismatch"}
        try:
            summary = json.loads(plaintext.decode("utf-8"))
        except Exception:
            return {"accepted": False, "reason": "invalid_payload"}
        if not isinstance(summary, dict):
            return {"accepted": False, "reason": "invalid_payload"}
        summary_id = str(summary.get("summary_id") or summary.get("id") or summary.get("file") or "").strip()
        if summary_id:
            summary["summary_id"] = summary_id
            if not self._remember_reflection(summary_id):
                return {"accepted": True, "duplicate": True, "summary_id": summary_id}
        summary["received_at"] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        if source:
            summary["received_from"] = source
        sender = payload.get("sender")
        if sender and "origin" not in summary:
            summary["origin"] = sender
        self._log_reflection(summary)
        self._publish_reflection_event(summary)
        return {"accepted": True, "summary_id": summary_id}

    def _sync_once(self) -> None:
        local_fragments = _local_fragments()
        nodes = list(registry.iter_remote_nodes())
        if not nodes:
            return
        for node in nodes:
            self._merge_from_node(node.serialise(), local_fragments)

    def _merge_from_node(self, node: Dict[str, object], local_cache: Dict[str, dict]) -> None:
        ip = node.get("ip")
        port = node.get("port", 5000)
        hostname = node.get("hostname", "unknown")
        if not ip:
            return
        url = f"http://{ip}:{port}{_MEMORY_ENDPOINT}"
        headers = {_HEADER_TOKEN: NODE_TOKEN}
        try:
            response = requests.get(url, headers=headers, timeout=_REMOTE_TIMEOUT)
        except requests.RequestException as exc:
            LOGGER.debug("Memory fetch from %s failed: %s", hostname, exc)
            return
        if response.status_code != 200:
            LOGGER.debug("Memory fetch from %s returned %s", hostname, response.status_code)
            return
        encoding = response.headers.get("Content-Encoding")
        payload = _decompress_payload(response.content, encoding)
        fragments = payload.get("fragments")
        if not isinstance(fragments, list):
            return
        updates = 0
        for fragment in fragments:
            if not isinstance(fragment, dict):
                continue
            fragment_id = fragment.get("id")
            if not fragment_id:
                continue
            remote_ts = _parse_timestamp(str(fragment.get("timestamp", "")))
            local_fragment = local_cache.get(str(fragment_id))
            local_ts = _parse_timestamp(str(local_fragment.get("timestamp", ""))) if local_fragment else 0.0
            if remote_ts and remote_ts <= local_ts:
                continue
            _write_fragment(fragment)
            local_cache[str(fragment_id)] = fragment
            updates += 1
        if updates:
            LOGGER.info("[Memory] Synced %s fragments from %s", updates, hostname)


synchronizer = DistributedMemorySynchronizer()

__all__ = ["DistributedMemorySynchronizer", "encode_payload", "synchronizer"]
