"""Distributed memory synchronisation across SentientOS nodes."""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional

import os
import requests
from dotenv import load_dotenv

import memory_manager as mm
from node_registry import NODE_TOKEN, registry

try:  # pragma: no cover - optional dependency
    import zstandard as zstd
except Exception:  # pragma: no cover - optional dependency
    zstd = None  # type: ignore

load_dotenv()

LOGGER = logging.getLogger(__name__)

_SYNC_INTERVAL_SECONDS = float(os.getenv("SENTIENTOS_MEMORY_SYNC_INTERVAL", "30"))
_REMOTE_TIMEOUT = 8.0
_HEADER_TOKEN = "X-Node-Token"
_MEMORY_ENDPOINT = "/memory/export"
_COMPRESSED_ENCODING = "base64+zstd"


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

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not NODE_TOKEN:
            LOGGER.warning("Memory federation requires NODE_TOKEN; skipping start.")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        banner = f"[SentientOS] Memory federation enabled (interval = {int(self._interval)} s)"
        LOGGER.info(banner)
        print(banner)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._sync_once()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Memory synchronisation step failed: %s", exc, exc_info=True)
            self._stop.wait(self._interval)

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
