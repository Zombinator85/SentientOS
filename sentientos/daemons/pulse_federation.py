"""Federated propagation and ingestion for the pulse bus."""

from __future__ import annotations

import base64
import binascii
import copy
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from . import pulse_bus

logger = logging.getLogger(__name__)

_KEYS_DIR_ENV = "PULSE_FEDERATION_KEYS_DIR"
_DEFAULT_KEYS_DIR = Path("/glow/federation_keys")
_REQUEST_TIMEOUT_SECONDS = 5
_FEDERATION_ENDPOINT = "/pulse/federation"


@dataclass(frozen=True)
class _Peer:
    name: str
    endpoint: str

    def api_base(self) -> str:
        base = self.endpoint.strip()
        if not base:
            return ""
        if "://" not in base:
            base = f"http://{base}"
        return base.rstrip("/")


_ENABLED = False
_PEER_MAP: dict[str, _Peer] = {}
_PEER_KEYS: dict[str, VerifyKey] = {}
_SUBSCRIPTION: pulse_bus.PulseSubscription | None = None


def _keys_dir() -> Path:
    override = os.getenv(_KEYS_DIR_ENV)
    if override:
        return Path(override)
    return _DEFAULT_KEYS_DIR


def _sanitize_name(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", value.strip())
    return sanitized or "peer"


def _normalize_peer(entry: object) -> _Peer | None:
    if isinstance(entry, str):
        endpoint = entry.strip()
        if not endpoint:
            return None
        name = _sanitize_name(endpoint)
        return _Peer(name=name, endpoint=endpoint)
    if isinstance(entry, dict):
        raw_name = entry.get("name") or entry.get("id") or entry.get("peer")
        raw_endpoint = (
            entry.get("url")
            or entry.get("endpoint")
            or entry.get("address")
            or entry.get("host")
        )
        endpoint = str(raw_endpoint or "").strip()
        if not endpoint:
            return None
        name_value = str(raw_name or endpoint)
        name = _sanitize_name(name_value)
        return _Peer(name=name, endpoint=endpoint)
    return None


def configure(*, enabled: bool, peers: Iterable[object] | None = None) -> None:
    """Configure federation state and subscriptions for the pulse bus."""

    global _ENABLED, _PEER_MAP

    _ENABLED = bool(enabled)
    normalized: dict[str, _Peer] = {}
    if peers is not None:
        for entry in peers:
            peer = _normalize_peer(entry)
            if peer is None:
                continue
            normalized[peer.name] = peer
    _PEER_MAP = normalized
    _load_peer_keys()
    _update_subscription()


def reset() -> None:
    """Disable federation support and drop cached peer state."""

    global _ENABLED, _PEER_MAP, _PEER_KEYS, _SUBSCRIPTION

    _ENABLED = False
    _PEER_MAP = {}
    _PEER_KEYS = {}
    if _SUBSCRIPTION is not None and _SUBSCRIPTION.active:
        _SUBSCRIPTION.unsubscribe()
    _SUBSCRIPTION = None


def is_enabled() -> bool:
    """Return whether federation support is currently enabled."""

    return _ENABLED and bool(_PEER_MAP)


def peers() -> Sequence[str]:
    """Return the configured federation peer names."""

    return tuple(_PEER_MAP.keys())


def verify_remote_signature(event: pulse_bus.PulseEvent, peer_name: str) -> bool:
    """Return ``True`` when ``event`` is signed by ``peer_name``."""

    key = _PEER_KEYS.get(peer_name)
    if key is None:
        return False
    signature = event.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    try:
        payload = pulse_bus._serialize_for_signature(event)
        key.verify(payload, base64.b64decode(signature))
        return True
    except (BadSignatureError, binascii.Error, ValueError):
        return False


def ingest_remote_event(event: pulse_bus.PulseEvent, peer_name: str) -> pulse_bus.PulseEvent:
    """Validate and ingest ``event`` from ``peer_name`` into the local bus."""

    if not _ENABLED:
        raise RuntimeError("Pulse federation is disabled")
    peer = _PEER_MAP.get(peer_name)
    if peer is None:
        raise ValueError(f"Unknown federation peer: {peer_name}")
    if not verify_remote_signature(event, peer_name):
        raise ValueError(f"Invalid signature from federation peer: {peer_name}")
    payload = copy.deepcopy(event)
    payload["source_peer"] = peer_name
    return pulse_bus.ingest(payload, source_peer=peer_name)


def request_recent_events(minutes: int) -> List[pulse_bus.PulseEvent]:
    """Request recent pulse history from all peers and ingest new events."""

    if not is_enabled():
        return []
    collected: List[pulse_bus.PulseEvent] = []
    for peer in _PEER_MAP.values():
        endpoint = peer.api_base()
        if not endpoint:
            continue
        try:
            response = _http_get(
                f"{endpoint}{_FEDERATION_ENDPOINT}",
                params={"minutes": minutes},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:  # pragma: no cover - network failures best-effort
            logger.warning("Failed to request pulse replay from peer %s", peer.name, exc_info=True)
            continue
        for event in _extract_events(response):
            try:
                ingested = ingest_remote_event(event, peer.name)
            except ValueError:
                logger.warning(
                    "Rejected invalid federated event from peer %s", peer.name, exc_info=True
                )
                continue
            collected.append(ingested)
    return collected


def _load_peer_keys() -> None:
    global _PEER_KEYS

    directory = _keys_dir()
    _PEER_KEYS = {}
    if not directory.exists():
        return
    for peer in _PEER_MAP.values():
        key_path = directory / f"{peer.name}.pub"
        try:
            key_bytes = key_path.read_bytes()
        except FileNotFoundError:
            logger.warning("Federation verify key missing for peer %s at %s", peer.name, key_path)
            continue
        try:
            _PEER_KEYS[peer.name] = VerifyKey(key_bytes)
        except Exception as exc:
            logger.warning("Unable to load federation key for %s: %s", peer.name, exc)


def _update_subscription() -> None:
    global _SUBSCRIPTION

    if not is_enabled():
        if _SUBSCRIPTION is not None and _SUBSCRIPTION.active:
            _SUBSCRIPTION.unsubscribe()
        _SUBSCRIPTION = None
        return
    if _SUBSCRIPTION is not None and _SUBSCRIPTION.active:
        return
    _SUBSCRIPTION = pulse_bus.subscribe(_handle_local_publish)


def _handle_local_publish(event: pulse_bus.PulseEvent) -> None:
    if not _ENABLED or not _PEER_MAP:
        return
    if str(event.get("source_peer", "local")) != "local":
        return
    if not _payload_is_safe(event):
        logger.warning("Skipping privileged pulse event; payload not federated")
        return
    for peer in _PEER_MAP.values():
        endpoint = peer.api_base()
        if not endpoint:
            continue
        try:
            _http_post(
                f"{endpoint}{_FEDERATION_ENDPOINT}",
                json=event,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:  # pragma: no cover - network failures best-effort
            logger.warning("Failed to forward pulse event to peer %s", peer.name, exc_info=True)


def _payload_is_safe(event: pulse_bus.PulseEvent) -> bool:
    try:
        payload = json.dumps(event, sort_keys=True)
    except (TypeError, ValueError):
        return False
    lowered = payload.lower()
    return "/vow" not in lowered and "newlegacy" not in lowered


def _extract_events(response: object) -> List[pulse_bus.PulseEvent]:
    if response is None:
        return []
    if isinstance(response, list):
        raw = response
    elif hasattr(response, "json") and callable(response.json):
        try:
            raw = response.json()
        except Exception:
            logger.warning("Failed to decode federated replay payload", exc_info=True)
            return []
    else:
        return []
    events: List[pulse_bus.PulseEvent] = []
    for item in raw:
        if isinstance(item, dict):
            events.append(copy.deepcopy(item))
    return events


def _http_post(url: str, *, json: pulse_bus.PulseEvent, timeout: int) -> None:
    requests.post(url, json=json, timeout=timeout)


def _http_get(url: str, *, params: dict[str, object], timeout: int):
    return requests.get(url, params=params, timeout=timeout)


__all__ = [
    "configure",
    "reset",
    "is_enabled",
    "peers",
    "verify_remote_signature",
    "ingest_remote_event",
    "request_recent_events",
]
