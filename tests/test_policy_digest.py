from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from policy_digest import build_policy_digest, policy_digest, policy_digest_reference
from scripts.tooling_status import policy_local_dev_permissive
from sentientos.codex_startup_guard import codex_startup_state
from sentientos.volatility_contract import CapabilityRouter, VolatilityLevel, default_volatility_states


def test_policy_digest_hash_is_stable() -> None:
    digest = build_policy_digest(
        policy_id="test",
        policy_version="1",
        declared_invariants=("alpha", "beta"),
        scope=("startup",),
    )

    assert digest.digest() == digest.digest()


def test_policy_digest_identical_doctrine_matches() -> None:
    first = build_policy_digest(
        policy_id="test",
        policy_version="1",
        declared_invariants=("alpha", "beta"),
        scope=("startup", "tooling"),
    )
    second = build_policy_digest(
        policy_id="test",
        policy_version="1",
        declared_invariants=("beta", "alpha"),
        scope=("tooling", "startup"),
    )

    assert first.digest() == second.digest()
    assert first.doctrine_hash == second.doctrine_hash


def test_policy_digest_modified_doctrine_changes_hash() -> None:
    first = build_policy_digest(
        policy_id="test",
        policy_version="1",
        declared_invariants=("alpha", "beta"),
        scope=("startup",),
    )
    second = build_policy_digest(
        policy_id="test",
        policy_version="1",
        declared_invariants=("alpha", "beta", "gamma"),
        scope=("startup",),
    )

    assert first.digest() != second.digest()
    assert first.doctrine_hash != second.doctrine_hash


def test_policy_digest_is_immutable() -> None:
    digest = policy_digest()

    with pytest.raises(FrozenInstanceError):
        digest.policy_version = "mutated"  # type: ignore[misc]


def test_enforcement_paths_expose_policy_reference() -> None:
    policy_ref = policy_digest_reference()

    startup_state = codex_startup_state()
    assert startup_state.policy_reference == policy_ref

    router = CapabilityRouter(default_volatility_states())
    route = router.route(state=VolatilityLevel.NORMAL, action="assist")
    assert route.policy_reference == policy_ref

    tooling_policy = policy_local_dev_permissive()
    assert tooling_policy.forward_metadata["policy_digest"] == policy_ref
