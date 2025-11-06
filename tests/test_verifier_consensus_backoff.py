import math
from importlib import reload

import pytest


@pytest.fixture
def consensus_state(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "0")
    import relay_app

    module = reload(relay_app)
    state = module._ConsensusState(job_id="job-1", quorum_k=2, quorum_n=2, participants=["node-a", "node-b"])
    return module, state


def test_exponential_backoff_with_jitter_and_cap(monkeypatch, consensus_state):
    module, state = consensus_state
    attempts = []

    def fake_uniform(_low, _high):
        attempts.append(len(attempts) + 1)
        return 0.1

    monkeypatch.setattr(module.random, "uniform", fake_uniform)

    base = module._SOLICIT_RETRY_BASE
    factor = module._SOLICIT_RETRY_FACTOR
    now = 100.0

    for attempt in range(1, module._SOLICIT_RETRY_MAX):
        state.record_retry("node-a", success=False, error=f"err-{attempt}", now=now)
        expected_delay = base * (factor ** (attempt - 1)) + 0.1
        target = state.retry_after["node-a"]
        assert math.isclose(target, now + expected_delay, rel_tol=1e-6)
        now = target

    # Additional failure keeps the retry at infinity.
    state.record_retry("node-a", success=False, error="final-error", now=now)
    assert state.retry_after["node-a"] == float("inf")
    assert state.retries_by_node["node-a"] == module._SOLICIT_RETRY_MAX

    # Success clears counters and error.
    state.record_retry("node-a", success=True, error=None, now=now)
    assert "node-a" not in state.retries_by_node
    assert "node-a" not in state.errors_by_node


def test_give_up_after_max_retries_or_cancel(monkeypatch, consensus_state):
    module, state = consensus_state
    host = "node-a"
    for _ in range(module._SOLICIT_RETRY_MAX):
        state.record_retry(host, success=False, error="oops")
    assert state.has_exhausted_retries(host) is True
    assert state.allows_retry(host) is False

    state.cancel(reason="operator-stop")
    assert state.status == "CANCELED"
    assert state.allows_retry(host) is False
    state.record_retry(host, success=True)
    assert host not in state.errors_by_node
    assert state.cancel_reason == "operator-stop"
