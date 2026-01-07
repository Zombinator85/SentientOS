from __future__ import annotations

import pytest

from sentientos.federation import enablement as federation_enablement
from tests.federation_skip_policy import FEDERATION_SKIP_INTENTS


def _skip_reason(marker: pytest.Mark | None) -> str | None:
    if marker is None:
        return None
    if marker.kwargs.get("reason"):
        return str(marker.kwargs["reason"])
    if marker.args:
        return str(marker.args[0])
    return None


def test_federation_enablement_default_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(federation_enablement.ENABLEMENT_ENV, raising=False)
    assert federation_enablement.is_enabled() is False


def test_federation_enablement_is_queryable() -> None:
    assert isinstance(federation_enablement.is_enabled(), bool)


def test_federation_skip_references_enablement(request: pytest.FixtureRequest) -> None:
    items = [
        item
        for item in request.session.items
        if item.module.__name__ in FEDERATION_SKIP_INTENTS
    ]
    assert items, "Expected federation transport tests to be collected."

    enabled = federation_enablement.is_enabled()

    for item in items:
        skip_marker = item.get_closest_marker("skip")
        if enabled:
            assert skip_marker is None, (
                f"Expected federation transport tests to run when "
                f"{federation_enablement.ENABLEMENT_ENV} is enabled."
            )
            continue
        assert skip_marker is not None, "Expected federation transport tests to be skipped by default."
        reason = _skip_reason(skip_marker)
        assert reason and reason.strip(), f"Missing skip reason for {item.nodeid}"
        assert federation_enablement.ENABLEMENT_ENV in reason


def test_federation_contract_blocks_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(federation_enablement.ENABLEMENT_ENV, raising=False)
    with pytest.raises(federation_enablement.FederationContractViolation):
        federation_enablement.assert_federation_contract("tests:disabled")


def test_federation_contract_requires_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(federation_enablement.ENABLEMENT_ENV, "true")
    with pytest.raises(federation_enablement.FederationContractViolation):
        federation_enablement.assert_federation_contract("tests:opt-in")

    with federation_enablement.federation_opt_in("tests"):
        federation_enablement.assert_federation_contract("tests:opt-in")


def test_legacy_bypass_is_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(federation_enablement.ENABLEMENT_ENV, raising=False)
    with pytest.raises(federation_enablement.FederationContractViolation):
        federation_enablement.assert_federation_contract("tests:legacy")
    with federation_enablement.legacy_federation_bypass("tests"):
        federation_enablement.assert_federation_contract("tests:legacy")
    with pytest.raises(federation_enablement.FederationContractViolation):
        federation_enablement.assert_federation_contract("tests:legacy")
