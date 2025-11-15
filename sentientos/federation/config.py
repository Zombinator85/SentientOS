"""Federation configuration parsing utilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, MutableMapping, Optional, Tuple

from .identity import NodeId, compute_fingerprint, build_node_id_payload

__all__ = ["PeerConfig", "FederationConfig", "load_federation_config"]

_LOGGER = logging.getLogger("sentientos.federation.config")


@dataclass
class PeerConfig:
    node_name: str
    state_file: str


@dataclass
class FederationConfig:
    enabled: bool
    node_id: NodeId
    state_file: str
    peers: List[PeerConfig]
    poll_interval_seconds: int
    max_drift_peers: int
    max_incompatible_peers: int
    max_missing_peers: int
    max_cathedral_ids: int = 0
    max_experiment_ids: int = 0


def _coerce_mapping(value: object) -> MutableMapping[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _normalise_state_file(path_value: object, runtime_root: Path) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(path_value, str) or not path_value:
        return None, "State file must be a non-empty string"
    raw_path = Path(path_value)
    if not raw_path.is_absolute():
        raw_path = runtime_root / raw_path
    try:
        resolved = raw_path.resolve()
    except OSError:
        resolved = raw_path
    state_dir = runtime_root / "federation" / "state"
    try:
        state_dir_resolved = state_dir.resolve()
    except OSError:
        state_dir_resolved = state_dir
    if state_dir_resolved not in resolved.parents and resolved != state_dir_resolved:
        return None, f"State file {resolved} must live under {state_dir_resolved}"
    return str(resolved), None


def load_federation_config(
    config: Mapping[str, object],
    *,
    runtime_root: Path,
) -> Tuple[FederationConfig, List[str]]:
    """Parse federation configuration returning config + warnings."""

    warnings: List[str] = []
    federation_section = _coerce_mapping(config.get("federation"))
    runtime_section = _coerce_mapping(config.get("runtime"))

    node_name = str(federation_section.get("node_name") or runtime_section.get("node_name") or "local-node")
    poll_interval = int(federation_section.get("poll_interval_seconds") or 10)
    drift_section = _coerce_mapping(federation_section.get("drift"))

    def _threshold(name: str, default: int) -> int:
        value = drift_section.get(name)
        if value in {None, ""}:
            return default
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            warnings.append(f"Invalid federation drift threshold for {name}; using {default}")
            return default
        if coerced < 0:
            warnings.append(f"federation drift threshold {name} must be non-negative; using {default}")
            return default
        return coerced

    max_drift_peers = _threshold("max_drift_peers", 0)
    max_incompatible_peers = _threshold("max_incompatible_peers", 0)
    max_missing_peers = _threshold("max_missing_peers", 0)
    enabled = bool(federation_section.get("enabled", False))

    indexes_section = federation_section.get("indexes")
    indexes_present = isinstance(indexes_section, Mapping)
    indexes = _coerce_mapping(indexes_section)

    def _index_limit(name: str, default: int) -> int:
        if not indexes_present:
            return 0
        value = indexes.get(name)
        if value in {None, ""}:
            return default
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            warnings.append(f"Invalid federation index limit for {name}; using {default}")
            return default
        if coerced < 0:
            warnings.append(f"Federation index limit {name} must be non-negative; using {default}")
            return default
        return coerced

    max_cathedral_ids = _index_limit("max_cathedral_ids", 64)
    max_experiment_ids = _index_limit("max_experiment_ids", 32)

    state_file_value = federation_section.get("state_file") or ""
    state_file, error = _normalise_state_file(state_file_value, runtime_root)
    if error:
        warnings.append(error)
        enabled = False
        state_dir = runtime_root / "federation" / "state"
        state_file = str(state_dir / f"{node_name}.json")

    runtime_root.mkdir(parents=True, exist_ok=True)
    state_dir = runtime_root / "federation" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    peers: List[PeerConfig] = []
    for raw_peer in federation_section.get("peers", []):
        if not isinstance(raw_peer, Mapping):
            warnings.append("Ignoring malformed peer entry; expected mapping")
            continue
        peer_name = str(raw_peer.get("node_name") or "").strip()
        if not peer_name:
            warnings.append("Peer entry missing node_name")
            continue
        peer_state_value = raw_peer.get("state_file")
        peer_state_file, peer_error = _normalise_state_file(peer_state_value, runtime_root)
        if peer_error:
            warnings.append(f"Peer {peer_name}: {peer_error}")
            continue
        peers.append(PeerConfig(node_name=peer_name, state_file=str(peer_state_file)))

    config_digest_source = _coerce_mapping(config)
    fingerprint = compute_fingerprint(
        node_name=node_name,
        runtime_root=runtime_root,
        config=config_digest_source,
    )
    node_id = build_node_id_payload(node_name, fingerprint)

    if warnings and enabled:
        _LOGGER.warning("Disabling federation due to configuration warnings: %s", warnings)
        enabled = False

    return (
        FederationConfig(
            enabled=enabled,
            node_id=node_id,
            state_file=str(state_file),
            peers=peers,
            poll_interval_seconds=max(1, poll_interval),
            max_drift_peers=max_drift_peers,
            max_incompatible_peers=max_incompatible_peers,
            max_missing_peers=max_missing_peers,
            max_cathedral_ids=max_cathedral_ids,
            max_experiment_ids=max_experiment_ids,
        ),
        warnings,
    )
