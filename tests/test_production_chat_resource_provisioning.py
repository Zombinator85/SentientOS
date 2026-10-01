"""Boundary tests for the production resource-provisioning consumer."""
from __future__ import annotations

import inspect

import pytest

from sentientos.production_chat_resource_provisioning import (
    MANIFEST_SCHEMA, ProductionChatResourceProvisioningError, manifest_digest_for,
    validate_resource_provisioning_id,
)

pytestmark = pytest.mark.no_legacy_skip


def test_manifest_digest_is_canonical_and_excludes_only_its_digest() -> None:
    body = {"schema_version": MANIFEST_SCHEMA, "provisioning_id": "production.v1"}
    first = manifest_digest_for(body)
    assert first == manifest_digest_for(dict(reversed(tuple(body.items()))))
    assert manifest_digest_for({**body, "manifest_digest": "sha256:" + "0" * 64}) == first
    assert first.startswith("sha256:") and len(first) == 71


@pytest.mark.parametrize("value", ["", "../escape", "a/b", "a\\b", ".", "..", "all", "any", "*", "UPPER"])
def test_provisioning_id_rejects_paths_aliases_and_wildcards(value: str) -> None:
    with pytest.raises(ProductionChatResourceProvisioningError, match="invalid_resource_provisioning_id"):
        validate_resource_provisioning_id(value)


def test_loader_source_is_consumer_only() -> None:
    import sentientos.production_chat_resource_provisioning as module
    source = inspect.getsource(module)
    assert ".issue(" not in source
    assert "mint_root(" not in source and "mint_root_with_provenance(" not in source
    assert "RootPrincipalIssuer(" not in source
    assert "PrivateKeyCustody" not in source and "ProvenanceSigner(" not in source
    assert "read_regular" in source and "fixed_object" in source
