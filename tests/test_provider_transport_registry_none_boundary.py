import pytest

from sentientos.context_hygiene.prompt_provider_transport_registry import (
    provider_transport_registry_is_null_only,
)

pytestmark = pytest.mark.no_legacy_skip


def test_missing_registry_manifest_is_rejected() -> None:
    assert provider_transport_registry_is_null_only(None) is False
