from datetime import datetime, timezone
from typing import Dict

from sentientos.cathedral.federation_guard import can_apply_amendment_now, should_accept_amendment
from sentientos.cathedral.amendment import Amendment
from sentientos.federation.identity import NodeId
from sentientos.federation.window import FederationWindow


def _window(**overrides) -> FederationWindow:
    base: Dict[str, object] = {
        "local_node": NodeId(name="local", fingerprint="fp"),
        "ts": datetime.now(timezone.utc),
        "peers": {},
        "ok_count": 0,
        "warn_count": 0,
        "drift_count": 0,
        "incompatible_count": 0,
        "missing_count": 0,
        "is_quorum_healthy": True,
        "is_cluster_unstable": False,
    }
    base.update(overrides)
    return FederationWindow(**base)  # type: ignore[arg-type]


def _amendment(risk: str) -> Amendment:
    return Amendment(
        id="amend-1",
        created_at=datetime.now(timezone.utc),
        proposer="tester",
        summary="Adjust setting",
        changes={"config": {"runtime": {"value": 1}}},
        reason="Routine update",
        risk_level=risk,
    )


def test_guard_allows_when_no_window() -> None:
    decision = should_accept_amendment(None, "high")
    assert decision == "allow"


def test_guard_holds_high_risk_when_unstable() -> None:
    window = _window(is_cluster_unstable=True)
    assert should_accept_amendment(window, "high") == "hold"
    assert should_accept_amendment(window, "medium") == "warn"
    assert should_accept_amendment(window, "low") == "allow"


def test_guard_warns_when_healthy_but_warns_present() -> None:
    window = _window(warn_count=1, drift_count=1)
    assert should_accept_amendment(window, "high") == "warn"
    assert should_accept_amendment(window, "medium") == "warn"
    assert should_accept_amendment(window, "low") == "allow"


def test_guard_defaults_to_caution_when_not_healthy() -> None:
    window = _window(is_quorum_healthy=False, warn_count=0, drift_count=0)
    assert should_accept_amendment(window, "high") == "hold"
    assert should_accept_amendment(window, "medium") == "warn"
    assert should_accept_amendment(window, "low") == "allow"


def test_can_apply_amendment_matches_allow_only() -> None:
    healthy_window = _window()
    amendment = _amendment("medium")
    assert can_apply_amendment_now(amendment, healthy_window) is True

    unstable_window = _window(is_cluster_unstable=True)
    assert can_apply_amendment_now(amendment, unstable_window) is False
