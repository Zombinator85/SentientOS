"""Persistent cluster node registry for SentientOS.

This module maintains a persistent record of nodes that participate in the
SentientOS distributed cognition fabric. Entries are stored under the
``SENTIENTOS_DATA_DIR`` (falling back to ``./sentientos_data``) inside the
``nodes`` directory. The registry tracks metadata announced by the discovery
beacons as well as manual registrations performed through the HTTP API.

Thread-safe access is provided so callers from Flask routes, background threads
and daemons can safely mutate the registry.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Optional

from dotenv import load_dotenv

from sentientos.storage import get_data_root

load_dotenv()

_DEFAULT_EXPIRY_SECONDS = 30.0
_REGISTRY_DIR_NAME = "nodes"
_REGISTRY_FILE_NAME = "nodes.json"


@dataclass
class NodeRecord:
    """Representation of a remote SentientOS node."""

    hostname: str
    ip: str
    port: int = 5000
    capabilities: Dict[str, object] = field(default_factory=dict)
    last_seen: float = field(default_factory=lambda: time.time())

    def serialise(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "hostname": self.hostname,
            "ip": self.ip,
            "port": self.port,
            "capabilities": dict(self.capabilities),
            "last_seen": self.last_seen,
        }
        return payload

    @classmethod
    def from_mapping(cls, payload: MutableMapping[str, object]) -> "NodeRecord":
        hostname = str(payload.get("hostname") or payload.get("id") or "")
        ip = str(payload.get("ip") or "")
        port = int(payload.get("port") or 5000)
        capabilities_obj = payload.get("capabilities") or {}
        if isinstance(capabilities_obj, dict):
            capabilities = dict(capabilities_obj)
        else:
            capabilities = {"value": capabilities_obj}
        last_seen = float(payload.get("last_seen") or time.time())
        return cls(hostname=hostname, ip=ip, port=port, capabilities=capabilities, last_seen=last_seen)


class NodeRegistry:
    """Persisted registry of active SentientOS nodes."""

    def __init__(self, storage_path: Path, *, expiry_seconds: float = _DEFAULT_EXPIRY_SECONDS) -> None:
        self._path = storage_path
        self._expiry = expiry_seconds
        self._lock = threading.RLock()
        self._nodes: Dict[str, NodeRecord] = {}
        self._local_hostname: Optional[str] = None
        self._load()

    @classmethod
    def default(cls) -> "NodeRegistry":
        root = get_data_root() / _REGISTRY_DIR_NAME
        root.mkdir(parents=True, exist_ok=True)
        return cls(root / _REGISTRY_FILE_NAME)

    def set_local_identity(self, hostname: str) -> None:
        with self._lock:
            self._local_hostname = hostname

    @property
    def local_hostname(self) -> Optional[str]:
        with self._lock:
            return self._local_hostname

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        records = payload if isinstance(payload, list) else payload.get("nodes")
        if not isinstance(records, list):
            return
        for entry in records:
            if not isinstance(entry, dict):
                continue
            record = NodeRecord.from_mapping(entry)
            self._nodes[record.hostname] = record

    def _save(self) -> None:
        data = [record.serialise() for record in self._nodes.values()]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # Persistence failures should not crash runtime discovery.
            pass

    def register_or_update(
        self,
        hostname: str,
        ip: str,
        *,
        port: int = 5000,
        capabilities: Optional[Dict[str, object]] = None,
        last_seen: Optional[float] = None,
    ) -> NodeRecord:
        """Record that ``hostname`` is reachable at ``ip``.

        Returns the updated :class:`NodeRecord` instance.
        """

        if not hostname:
            raise ValueError("hostname is required for node registration")
        if not ip:
            raise ValueError("ip is required for node registration")
        timestamp = last_seen if last_seen is not None else time.time()
        with self._lock:
            record = self._nodes.get(hostname)
            if record is None:
                record = NodeRecord(hostname=hostname, ip=ip, port=port, capabilities=capabilities or {}, last_seen=timestamp)
                self._nodes[hostname] = record
            else:
                record.ip = ip
                record.port = port
                if capabilities:
                    record.capabilities = dict(capabilities)
                record.last_seen = max(timestamp, record.last_seen)
            self._save()
            return record

    def prune(self) -> None:
        threshold = time.time() - self._expiry
        removed: List[str] = []
        with self._lock:
            for hostname, record in list(self._nodes.items()):
                if record.last_seen < threshold:
                    removed.append(hostname)
                    self._nodes.pop(hostname, None)
            if removed:
                self._save()

    def active_nodes(self) -> List[Dict[str, object]]:
        self.prune()
        with self._lock:
            return [record.serialise() for record in sorted(self._nodes.values(), key=lambda r: r.last_seen, reverse=True)]

    def iter_remote_nodes(self) -> Iterable[NodeRecord]:
        self.prune()
        with self._lock:
            for record in sorted(self._nodes.values(), key=lambda r: r.last_seen, reverse=True):
                if self._local_hostname and record.hostname == self._local_hostname:
                    continue
                yield record

    def get(self, hostname: str) -> Optional[NodeRecord]:
        with self._lock:
            return self._nodes.get(hostname)


class RoundRobinRouter:
    """Utility that cycles through active nodes using the registry."""

    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self._lock = threading.Lock()
        self._index = 0

    def next(self) -> Optional[NodeRecord]:
        candidates = list(self._registry.iter_remote_nodes())
        if not candidates:
            return None
        with self._lock:
            node = candidates[self._index % len(candidates)]
            self._index = (self._index + 1) % len(candidates)
        return node


registry = NodeRegistry.default()

NODE_TOKEN = os.getenv("NODE_TOKEN", "")

__all__ = [
    "NodeRecord",
    "NodeRegistry",
    "RoundRobinRouter",
    "registry",
    "NODE_TOKEN",
]
