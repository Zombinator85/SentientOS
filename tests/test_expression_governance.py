from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

import pytest

from codex import (
    BridgeState,
    CapabilityExpiredError,
    CapabilityScopeError,
    ExpressionBridge,
    ExpressionReplayError,
    ExpressionSchemaError,
    IntentDraftLedger,
    PublishWindowClosedError,
    ReadinessBand,
)


pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture(autouse=True)
def _clean_expression_files() -> None:
    fingerprint_path = Path(tempfile.gettempdir()) / "expression_bridge_fingerprints.log"
    lock_path = Path(tempfile.gettempdir()) / "expression_bridge.lock"
    for path in (fingerprint_path, lock_path):
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    yield
    for path in (fingerprint_path, lock_path):
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


class DualClock:
    def __init__(self) -> None:
        self._now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self._monotonic = 0.0

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds

    def skew_wall(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic


def _mature_draft(clock: DualClock):
    ledger = IntentDraftLedger(
        expire_after=timedelta(minutes=15),
        decay_after=timedelta(minutes=5),
        evaluator=None,
        now=clock.now,
    )
    draft = ledger.append(
        label="stable reflection",
        trigger="audit",
        confidence=0.8,
        volatility=0.05,
    )
    clock.advance(2)
    ledger.reaffirm(draft.draft_id)
    draft.readiness = ReadinessBand.MATURE
    draft.non_executable = False
    return draft


def test_capability_expiration_and_scope_enforcement() -> None:
    clock = DualClock()
    bridge = ExpressionBridge(
        now=clock.now,
        monotonic=clock.monotonic,
        require_capability_for={"governed"},
    )
    bridge.arm(reason="test")
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="governed expression",
        epistemic_basis="audit",
        confidence_band="stable",
        expression_type="governed",
    )

    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    with pytest.raises(CapabilityScopeError):
        bridge.emit(artifact, platform="alpha")

    capability = bridge.issue_capability(scope="governed", ttl=timedelta(seconds=1), issuer="auditor")
    clock.advance(2)
    with pytest.raises(CapabilityExpiredError):
        bridge.emit(artifact, platform="alpha", capability=capability)

    wrong_scope = bridge.issue_capability(scope="other", ttl=timedelta(seconds=5), issuer="auditor")
    with pytest.raises(CapabilityScopeError):
        bridge.emit(artifact, platform="alpha", capability=wrong_scope)

    assert any(entry["suppression_reason"] == "capability-missing" for entry in bridge.forensic_ring())


def test_epoch_change_prevents_cross_boot_replay() -> None:
    clock = DualClock()
    bridge = ExpressionBridge(now=clock.now, monotonic=clock.monotonic)
    bridge.arm(reason="epoch-one")
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="first emission",
        epistemic_basis="reviewed",
        confidence_band="stable",
    )
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    fingerprint = bridge.emit(artifact, platform="alpha")

    restarted = ExpressionBridge(now=clock.now, monotonic=clock.monotonic)
    restarted.arm(reason="epoch-two")
    restarted.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    with pytest.raises(ExpressionReplayError):
        restarted.emit(artifact, platform="beta")

    assert fingerprint["epoch_id"] != restarted._epoch_id
    assert fingerprint["monotonic_window"].isdigit()


def test_wall_clock_skew_uses_monotonic_fallback() -> None:
    clock = DualClock()
    bridge = ExpressionBridge(
        now=clock.now,
        monotonic=clock.monotonic,
        wall_clock_drift_epsilon=timedelta(seconds=0.1),
    )
    bridge.arm(reason="drift")
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="drift protected",
        epistemic_basis="manual",
        confidence_band="stable",
    )

    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=20))
    clock.skew_wall(10)
    fingerprint = bridge.emit(artifact, platform="alpha")

    assert fingerprint["timestamp_source"] == "monotonic"


def test_schema_validation_blocks_malformed_payload() -> None:
    clock = DualClock()
    bridge = ExpressionBridge(
        now=clock.now,
        monotonic=clock.monotonic,
        require_capability_for={"typed"},
    )
    bridge.register_schema(expression_type="typed", validator=lambda payload: payload["body"])
    bridge.arm(reason="schema")
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="structured",
        epistemic_basis="manual",
        confidence_band="stable",
        expression_type="typed",
    )
    capability = bridge.issue_capability(scope="typed", ttl=timedelta(seconds=5), issuer="auditor")
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))

    with pytest.raises(ExpressionSchemaError):
        bridge.emit(artifact, platform="alpha", capability=capability, payload={"missing": True})

    assert bridge._capability_usage.get(capability.nonce, 0) == 0


def test_ring_buffer_bounds_and_hash_only_entries() -> None:
    bridge = ExpressionBridge(ring_buffer_size=3)
    bridge.arm(reason="buffer")
    for idx in range(5):
        bridge._record_ring_buffer(artifact_hash=str(idx), platform="probe", reason="test")

    ring = bridge.forensic_ring()
    assert len(ring) == 3
    assert all("fingerprint_hash" in entry and entry["fingerprint_hash"] for entry in ring)
    assert all("suppression_reason" in entry for entry in ring)
    assert not any("content" in entry for entry in ring)


def test_quiet_to_armed_to_killed_transitions_are_audited() -> None:
    bridge = ExpressionBridge()
    assert bridge.state() == BridgeState.QUIET
    assert bridge.state_log()[0]["reason"] == "init"

    bridge.arm(reason="operator")
    bridge.kill(reason="shutdown")
    bridge.quiet(reason="ignored")

    assert bridge.state() == BridgeState.KILLED
    assert bridge.state_log()[-1]["state"] == BridgeState.KILLED
    assert len(bridge.state_log()) == 3
    bridge.arm(reason="post-kill")
    assert bridge.state() == BridgeState.KILLED


def test_fork_and_replay_safety_survives_new_epoch() -> None:
    clock = DualClock()
    bridge = ExpressionBridge(now=clock.now, monotonic=clock.monotonic)
    bridge.arm(reason="fork")
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="fork safe",
        epistemic_basis="manual",
        confidence_band="stable",
    )
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    bridge.emit(artifact, platform="alpha")

    restarted = ExpressionBridge(now=clock.now, monotonic=clock.monotonic)
    restarted.arm(reason="fork-restart")
    restarted.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    with pytest.raises(ExpressionReplayError):
        restarted.emit(artifact, platform="alpha")


def test_quiet_state_blocks_emission_until_armed() -> None:
    clock = DualClock()
    bridge = ExpressionBridge(now=clock.now, monotonic=clock.monotonic)
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="needs arming",
        epistemic_basis="manual",
        confidence_band="stable",
    )
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    with pytest.raises(PublishWindowClosedError):
        bridge.emit(artifact, platform="alpha")

    bridge.arm(reason="now-armed")
    bridge.emit(artifact, platform="alpha")
