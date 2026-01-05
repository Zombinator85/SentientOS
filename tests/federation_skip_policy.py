"""Federation skip intent policy for auditable test gating."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FederationSkipCategory(str, Enum):
    FEATURE_DISABLED = "feature-disabled"
    INTEGRATION_REQUIRED = "integration-required"
    ENVIRONMENT_DEPENDENT = "environment-dependent"
    DEPRECATED_PENDING = "deprecated/pending behavior"


@dataclass(frozen=True)
class FederationSkipIntent:
    category: FederationSkipCategory
    reason: str


FEDERATION_SKIP_INTENTS = {
    "tests.test_federation_transport": FederationSkipIntent(
        category=FederationSkipCategory.DEPRECATED_PENDING,
        reason=(
            "Federation transport unit coverage is quarantined behind the legacy marker "
            "until the transport suite is promoted; run with -m legacy to execute."
        ),
    ),
    "tests.test_federation_transport_guard": FederationSkipIntent(
        category=FederationSkipCategory.DEPRECATED_PENDING,
        reason=(
            "Federation transport guard checks remain in the legacy suite; "
            "run with -m legacy to execute."
        ),
    ),
}


__all__ = ["FEDERATION_SKIP_INTENTS", "FederationSkipCategory", "FederationSkipIntent"]
