"""Explicit federation enablement signal."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Mapping
import contextvars
import os
import sys

ENABLEMENT_ENV = "SENTIENTOS_FEDERATION_ENABLED"
FEDERATION_METADATA_KEYS = frozenset({"federation_envelope", "handshake", "attestation"})

_FEDERATION_OPT_IN = contextvars.ContextVar("federation_opt_in", default=False)
_FEDERATION_LEGACY_BYPASS = contextvars.ContextVar("federation_legacy_bypass", default=False)


class FederationContractViolation(RuntimeError):
    """Raised when federation access violates the system contract."""


def is_enabled() -> bool:
    """Return True when federation is explicitly enabled."""
    value = os.getenv(ENABLEMENT_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def has_federation_artifacts(metadata: Mapping[str, object] | None) -> bool:
    if not metadata:
        return False
    return any(key in metadata for key in FEDERATION_METADATA_KEYS)


def is_opted_in() -> bool:
    return bool(_FEDERATION_OPT_IN.get())


def is_legacy_bypass_active() -> bool:
    return bool(_FEDERATION_LEGACY_BYPASS.get())


def assert_federation_contract(context: str) -> None:
    if not isinstance(context, str) or not context.strip():
        raise FederationContractViolation("Federation contract context must be a non-empty string.")
    if is_legacy_bypass_active():
        return
    if not is_enabled():
        raise FederationContractViolation(
            f"Federation access blocked ({context}): enablement is disabled."
        )
    if not is_opted_in():
        raise FederationContractViolation(
            f"Federation access blocked ({context}): explicit opt-in is required."
        )


@contextmanager
def federation_opt_in(reason: str | None = None):
    """Explicit federation opt-in context for deliberate enablement."""
    _ = reason
    token = _FEDERATION_OPT_IN.set(True)
    try:
        yield
    finally:
        _FEDERATION_OPT_IN.reset(token)


@contextmanager
def legacy_federation_bypass(reason: str | None = None):
    """Test-only legacy bypass for federation contract enforcement."""
    _ = reason
    if "PYTEST_CURRENT_TEST" not in os.environ and "pytest" not in sys.modules:
        raise FederationContractViolation("Legacy federation bypass is restricted to tests.")
    token = _FEDERATION_LEGACY_BYPASS.set(True)
    try:
        yield
    finally:
        _FEDERATION_LEGACY_BYPASS.reset(token)


__all__ = [
    "ENABLEMENT_ENV",
    "FEDERATION_METADATA_KEYS",
    "FederationContractViolation",
    "assert_federation_contract",
    "federation_opt_in",
    "has_federation_artifacts",
    "is_enabled",
    "is_legacy_bypass_active",
    "is_opted_in",
    "legacy_federation_bypass",
]
