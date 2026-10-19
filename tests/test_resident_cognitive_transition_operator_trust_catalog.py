from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.resident_cognitive_transition_operator_trust_catalog import (
    CATALOG_SCHEMA, ReadOnlyTransitionOperatorTrustCatalog,
    TransitionOperatorTrustCatalogError, catalog_digest_for,
)

pytestmark = pytest.mark.no_legacy_skip


def _catalog() -> tuple[bytes, str, str]:
    public = Ed25519PrivateKey.from_private_bytes(bytes(range(32))).public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    public_text = base64.urlsafe_b64encode(public).decode("ascii").rstrip("=")
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    body = {"schema": CATALOG_SCHEMA, "catalog_version": 7, "entries": [{
        "operator_identity": "operator-1", "signing_key_id": key_id,
        "algorithm": "ed25519", "public_key": public_text,
        "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2027-01-01T00:00:00Z",
        "revocation_status": "active",
    }]}
    value = {**body, "catalog_digest": catalog_digest_for(body)}
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(), key_id, value["catalog_digest"]


def test_catalog_load_is_version_and_digest_bound_and_lookup_only() -> None:
    raw, key_id, catalog_digest = _catalog()
    catalog = ReadOnlyTransitionOperatorTrustCatalog.from_bytes(
        raw, expected_catalog_version=7, expected_catalog_digest=catalog_digest)
    entry = catalog.lookup(operator_identity="operator-1", signing_key_id=key_id, algorithm="ed25519")
    assert entry is not None and entry.revocation_status == "active"
    assert catalog.lookup(operator_identity="operator-1", signing_key_id=key_id,
                          algorithm="other") is None
    assert not hasattr(catalog, "enroll")
    with pytest.raises(TransitionOperatorTrustCatalogError, match="catalog_digest_mismatch"):
        ReadOnlyTransitionOperatorTrustCatalog.from_bytes(
            raw, expected_catalog_version=7, expected_catalog_digest="sha256:" + "0" * 64)


def test_catalog_rejects_noncanonical_and_duplicate_trust_tuples() -> None:
    raw, key_id, catalog_digest = _catalog()
    with pytest.raises(TransitionOperatorTrustCatalogError, match="catalog_not_canonical"):
        ReadOnlyTransitionOperatorTrustCatalog.from_bytes(
            raw + b" ", expected_catalog_version=7, expected_catalog_digest=catalog_digest)
    value = json.loads(raw)
    value["entries"].append(dict(value["entries"][0]))
    value["catalog_digest"] = catalog_digest_for(value)
    duplicate = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    with pytest.raises(TransitionOperatorTrustCatalogError, match="catalog_trust_tuple_duplicate"):
        ReadOnlyTransitionOperatorTrustCatalog.from_bytes(
            duplicate, expected_catalog_version=7, expected_catalog_digest=value["catalog_digest"])

