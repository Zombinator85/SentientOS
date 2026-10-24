"""Compose read-only Federation peer Health sources from protected local pins.

The pin file is installation-owned configuration, not peer-provided evidence.
Its operating-system custody selects the exact per-peer catalog bytes. This
module does not enroll peers, create a transport, admit work, or mutate Health.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Iterable, Mapping
from types import MappingProxyType

from sentientos.windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

from .peer_authentication_ed25519 import CryptographyEd25519FederationPeerSignatureVerifier
from .peer_replay_owner import FederationPeerReplayOwner, FederationPeerReplayOwnerError
from .peer_trust_catalog import (
    FederationPeerTrustCatalogError,
    ReadOnlyFederationPeerTrustCatalog,
)
from .poller import PeerHealthRecoverySource

PIN_SCHEMA = "sentientos.federation_peer_health_trust_pin:v1"
_PIN_FIELDS = frozenset({"schema", "peers"})
_PEER_FIELDS = frozenset({"peer_id", "catalog_version", "catalog_digest", "max_age_seconds"})
_PEER_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_PIN_BYTES = 65_536
_MAX_PIN_PEERS = 1024
_MAX_PEER_AGE_SECONDS = 86_400


class FederationPeerHealthSourceFactoryError(ValueError):
    """A pin, platform, trust catalog, or peer composition failed closed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _PeerPin:
    peer_id: str
    catalog_version: int
    catalog_digest: str
    max_age_seconds: int


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise FederationPeerHealthSourceFactoryError("peer_health_pin_nonfinite_number")


def _supports_replay_owner_custody() -> bool:
    return bool(
        os.name == "posix"
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and os.open in os.supports_dir_fd
    )


def _load_pin(path: Path) -> tuple[_PeerPin, ...]:
    if not path.is_absolute():
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_path_must_be_absolute")
    try:
        raw = read_explicit_file(path, max_bytes=_MAX_PIN_BYTES, require_private_acl=True)
    except (WindowsHandleCustodyError, OSError) as exc:
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_custody_invalid") from exc
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
                           parse_constant=_reject_constant)
    except FederationPeerHealthSourceFactoryError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_load_failed") from exc
    if not isinstance(value, dict) or set(value) != _PIN_FIELDS:
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_fields_invalid")
    if value.get("schema") != PIN_SCHEMA:
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_schema_invalid")
    rows = value.get("peers")
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_PIN_PEERS:
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_peers_invalid")
    try:
        canonical = _canonical(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_content_invalid") from exc
    if canonical != raw:
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_not_canonical")

    pins: list[_PeerPin] = []
    seen: set[str] = set()
    previous_peer_id: str | None = None
    for row in rows:
        if not isinstance(row, dict) or set(row) != _PEER_FIELDS:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_peer_fields_invalid")
        peer_id = row.get("peer_id")
        version = row.get("catalog_version")
        digest = row.get("catalog_digest")
        max_age = row.get("max_age_seconds")
        if not isinstance(peer_id, str) or _PEER_ID.fullmatch(peer_id) is None:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_peer_id_invalid")
        if peer_id in seen:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_peer_duplicate")
        if previous_peer_id is not None and peer_id <= previous_peer_id:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_peers_not_sorted")
        if type(version) is not int or version < 1:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_catalog_version_invalid")
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_catalog_digest_invalid")
        if type(max_age) is not int or not 1 <= max_age <= _MAX_PEER_AGE_SECONDS:
            raise FederationPeerHealthSourceFactoryError("peer_health_pin_max_age_invalid")
        pins.append(_PeerPin(peer_id, version, digest, max_age))
        seen.add(peer_id)
        previous_peer_id = peer_id
    return tuple(pins)


def load_operator_pinned_peer_health_sources(
    pin_path: str | Path,
    *,
    runtime_root: str | Path,
    configured_peer_ids: Iterable[str],
) -> Mapping[str, PeerHealthRecoverySource]:
    """Load private operator pins and compose one immutable source per pinned peer.

    The per-peer trust catalog is fixed at
    ``<runtime_root>/federation/peer_trust_catalogs/<peer_id>.json``. Replay
    custody is fixed at ``<runtime_root>/federation/peer_health_replay/<peer_id>``.
    No directories are created here; the replay owner creates private custody
    only when a separately invoked acceptance operation writes an event.
    """
    if not isinstance(pin_path, (str, Path)):
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_path_invalid")
    if isinstance(configured_peer_ids, (str, bytes)):
        raise FederationPeerHealthSourceFactoryError("peer_health_configured_peer_ids_invalid")
    if not _supports_replay_owner_custody():
        raise FederationPeerHealthSourceFactoryError("peer_replay_owner_custody_unsupported")
    root = Path(runtime_root)
    if not root.is_absolute():
        raise FederationPeerHealthSourceFactoryError("peer_health_runtime_root_must_be_absolute")
    peer_ids = tuple(configured_peer_ids)
    if any(not isinstance(peer_id, str) or _PEER_ID.fullmatch(peer_id) is None for peer_id in peer_ids):
        raise FederationPeerHealthSourceFactoryError("peer_health_configured_peer_id_invalid")
    configured = frozenset(peer_ids)
    pins = _load_pin(Path(pin_path))
    if any(pin.peer_id not in configured for pin in pins):
        raise FederationPeerHealthSourceFactoryError("peer_health_pin_peer_not_configured")

    sources: dict[str, PeerHealthRecoverySource] = {}
    for pin in pins:
        catalog_path = root / "federation" / "peer_trust_catalogs" / f"{pin.peer_id}.json"
        try:
            catalog = ReadOnlyFederationPeerTrustCatalog.load(
                catalog_path,
                expected_catalog_version=pin.catalog_version,
                expected_catalog_digest=pin.catalog_digest,
            )
        except FederationPeerTrustCatalogError as exc:
            raise FederationPeerHealthSourceFactoryError("peer_health_trust_catalog_invalid") from exc
        if catalog.peer_ids != frozenset({pin.peer_id}):
            raise FederationPeerHealthSourceFactoryError("peer_health_trust_catalog_identity_mismatch")
        owner_path = root / "federation" / "peer_health_replay" / pin.peer_id
        try:
            owner = FederationPeerReplayOwner(owner_path, peer_id=pin.peer_id)
        except FederationPeerReplayOwnerError as exc:
            raise FederationPeerHealthSourceFactoryError("peer_health_replay_owner_invalid") from exc
        sources[pin.peer_id] = PeerHealthRecoverySource(
            owner=owner,
            catalog=catalog,
            signature_verifier=CryptographyEd25519FederationPeerSignatureVerifier(),
            max_age_seconds=pin.max_age_seconds,
        )
    return MappingProxyType(sources)


__all__ = [
    "FederationPeerHealthSourceFactoryError",
    "PIN_SCHEMA",
    "load_operator_pinned_peer_health_sources",
]
