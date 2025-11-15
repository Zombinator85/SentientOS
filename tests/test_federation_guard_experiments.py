from datetime import datetime, timezone
from typing import Dict

from sentientos.experiments.federation_guard import should_run_experiment
from sentientos.federation.identity import NodeId
from sentientos.federation.window import FederationWindow


def _window(**overrides) -> FederationWindow:
    base: Dict[str, object] = {
        "local_node": NodeId(name="node", fingerprint="fp"),
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


def test_experiment_guard_allows_without_window() -> None:
    assert should_run_experiment(None, "high") == "allow"


def test_experiment_guard_holds_high_risk_when_unstable() -> None:
    window = _window(is_cluster_unstable=True)
    assert should_run_experiment(window, "high") == "hold"
    assert should_run_experiment(window, "medium") == "warn"
    assert should_run_experiment(window, "low") == "allow"


def test_experiment_guard_warns_when_drift_present() -> None:
    window = _window(warn_count=1, drift_count=1)
    assert should_run_experiment(window, "high") == "warn"
    assert should_run_experiment(window, "medium") == "warn"
    assert should_run_experiment(window, "low") == "allow"


def test_experiment_guard_defaults_to_caution_when_not_healthy() -> None:
    window = _window(is_quorum_healthy=False, warn_count=0, drift_count=0)
    assert should_run_experiment(window, "high") == "hold"
    assert should_run_experiment(window, "medium") == "warn"
    assert should_run_experiment(window, "low") == "allow"
