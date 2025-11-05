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
    roles: List[str] = field(default_factory=list)
    token_hash: Optional[str] = None
    pubkey_fingerprint: Optional[str] = None
    trust_level: str = "provisional"
    last_seen: float = field(default_factory=lambda: time.time())
    upstream_host: Optional[str] = None

    def serialise(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "hostname": self.hostname,
            "ip": self.ip,
            "port": self.port,
            "capabilities": dict(self.capabilities),
            "roles": list(self.roles),
            "token_hash": self.token_hash,
            "pubkey_fingerprint": self.pubkey_fingerprint,
            "trust_level": self.trust_level,
            "last_seen": self.last_seen,
            "upstream_host": self.upstream_host,
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
        roles_obj = payload.get("roles")
        if isinstance(roles_obj, (list, tuple)):
            roles = [str(r) for r in roles_obj]
        elif isinstance(roles_obj, str):
            roles = [roles_obj]
        else:
            roles = []
        trust_level = str(payload.get("trust_level") or "provisional")
        token_hash = payload.get("token_hash")
        if token_hash is not None:
            token_hash = str(token_hash)
        pubkey_fingerprint = payload.get("pubkey_fingerprint")
        if pubkey_fingerprint is not None:
            pubkey_fingerprint = str(pubkey_fingerprint)
        upstream_host = payload.get("upstream_host")
        if upstream_host is not None:
            upstream_host = str(upstream_host)
        return cls(
            hostname=hostname,
            ip=ip,
            port=port,
            capabilities=capabilities,
            roles=roles,
            token_hash=token_hash,
            pubkey_fingerprint=pubkey_fingerprint,
            trust_level=trust_level,
            last_seen=last_seen,
            upstream_host=upstream_host,
        )

    @property
    def capability_keys(self) -> List[str]:
        keys: List[str] = []
        for key, value in self.capabilities.items():
            if isinstance(value, bool) and value:
                keys.append(str(key))
            elif value not in (None, False, "", 0):
                keys.append(str(key))
        return sorted(set(keys))


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
        roles: Optional[Iterable[str]] = None,
        token_hash: Optional[str] = None,
        pubkey_fingerprint: Optional[str] = None,
        trust_level: Optional[str] = None,
        upstream_host: Optional[str] = None,
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
                record = NodeRecord(
                    hostname=hostname,
                    ip=ip,
                    port=port,
                    capabilities=capabilities or {},
                    roles=list(roles) if roles else [],
                    token_hash=token_hash,
                    pubkey_fingerprint=pubkey_fingerprint,
                    trust_level=trust_level or "provisional",
                    last_seen=timestamp,
                    upstream_host=upstream_host,
                )
                self._nodes[hostname] = record
            else:
                record.ip = ip
                record.port = port
                if capabilities:
                    record.capabilities = dict(capabilities)
                if roles is not None:
                    record.roles = [str(role) for role in roles]
                if token_hash is not None:
                    record.token_hash = token_hash
                if pubkey_fingerprint is not None:
                    record.pubkey_fingerprint = pubkey_fingerprint
                if trust_level is not None:
                    record.trust_level = trust_level
                if upstream_host is not None:
                    record.upstream_host = upstream_host
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

    def iter_remote_nodes(
        self,
        *,
        capability: Optional[str] = None,
        roles: Optional[Iterable[str]] = None,
        trusted_only: bool = False,
    ) -> Iterable[NodeRecord]:
        self.prune()
        required_roles = {str(role) for role in roles or []}
        with self._lock:
            for record in sorted(self._nodes.values(), key=lambda r: r.last_seen, reverse=True):
                if self._local_hostname and record.hostname == self._local_hostname:
                    continue
                if record.trust_level == "blocked":
                    continue
                if trusted_only and record.trust_level != "trusted":
                    continue
                if capability and capability not in record.capability_keys:
                    continue
                if required_roles and not (required_roles & set(record.roles)):
                    continue
                yield record

    def get(self, hostname: str) -> Optional[NodeRecord]:
        with self._lock:
            return self._nodes.get(hostname)

    def set_trust_level(self, hostname: str, trust_level: str) -> Optional[NodeRecord]:
        trust_level = str(trust_level)
        with self._lock:
            record = self._nodes.get(hostname)
            if not record:
                return None
            record.trust_level = trust_level
            self._save()
            return record

    def store_token(self, hostname: str, token_hash: str) -> Optional[NodeRecord]:
        with self._lock:
            record = self._nodes.get(hostname)
            if not record:
                return None
            record.token_hash = token_hash
            self._save()
            return record

    def capability_map(self) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        with self._lock:
            for record in self._nodes.values():
                if record.trust_level == "blocked":
                    continue
                for key in record.capability_keys:
                    mapping.setdefault(key, []).append(record.hostname)
        for key in mapping:
            mapping[key].sort()
        return mapping


class RoundRobinRouter:
    """Utility that cycles through active nodes using the registry."""

    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self._lock = threading.Lock()
        self._indices: Dict[str, int] = {}

    def next(
        self,
        capability: Optional[str] = None,
        *,
        trusted_only: bool = True,
        roles: Optional[Iterable[str]] = None,
    ) -> Optional[NodeRecord]:
        key = capability or "__all__"
        candidates = list(
            self._registry.iter_remote_nodes(
                capability=capability,
                trusted_only=trusted_only,
                roles=roles,
            )
        )
        if not candidates:
            return None
        with self._lock:
            index = self._indices.get(key, 0)
            node = candidates[index % len(candidates)]
            self._indices[key] = (index + 1) % len(candidates)
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
