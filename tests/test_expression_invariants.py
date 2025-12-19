from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import multiprocessing
import tempfile
from pathlib import Path
from threading import Thread
from typing import List

import pytest

from codex import (
    ExpressionArtifact,
    ExpressionBridge,
    ExpressionReplayError,
    IntentDraftLedger,
    PublishWindowClosedError,
    ReadinessBand,
)


pytestmark = pytest.mark.no_legacy_skip


class FakeClock:
    def __init__(self) -> None:
        self._now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)

    def now(self) -> datetime:
        return self._now


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


def _mature_draft(clock: FakeClock):
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


def _crystallized(clock: FakeClock) -> tuple[ExpressionBridge, ExpressionArtifact]:
    bridge = ExpressionBridge(now=clock.now)
    bridge.arm(reason="test")
    draft = _mature_draft(clock)
    artifact = bridge.crystallize(
        draft,
        content="One-way status broadcast",
        epistemic_basis="operator approved",
        confidence_band="stable",
    )
    return bridge, artifact


def test_publish_window_requires_human_and_does_not_auto_open() -> None:
    clock = FakeClock()
    bridge = ExpressionBridge(now=clock.now)

    with pytest.raises(ValueError):
        bridge.open_window(opened_by="   ", ttl=timedelta(seconds=5))

    assert bridge._window is None


def test_windows_close_and_do_not_survive_restart() -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="operator", ttl=timedelta(seconds=2))
    bridge.emit(artifact, platform="status")

    with pytest.raises(PublishWindowClosedError):
        bridge.emit(artifact, platform="status")

    fresh_bridge = ExpressionBridge(now=clock.now)
    assert fresh_bridge._window is None
    assert fresh_bridge.emission_log() == []


def test_artifact_is_immutable_and_single_use(monkeypatch) -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="human", ttl=timedelta(seconds=5))
    bridge.emit(artifact, platform="status")

    with pytest.raises(FrozenInstanceError):
        artifact.content = "mutated"  # type: ignore[misc]

    bridge.open_window(opened_by="human", ttl=timedelta(seconds=5))
    with pytest.raises(ExpressionReplayError):
        bridge.emit(artifact, platform="secondary")


def test_artifact_cannot_be_duplicated_across_platforms(monkeypatch) -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    bridge.emit(artifact, platform="alpha")

    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    with pytest.raises(ExpressionReplayError):
        bridge.emit(artifact, platform="beta")


def test_bridge_enforces_artifact_and_timeout() -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="operator", ttl=timedelta(seconds=1))

    with pytest.raises(TypeError):
        bridge.emit(None, platform="log")  # type: ignore[arg-type]

    clock.advance(5)
    with pytest.raises(PublishWindowClosedError):
        bridge.emit(artifact, platform="log")


def test_kill_switch_blocks_opening(monkeypatch) -> None:
    monkeypatch.setenv("EXPRESSION_DISABLED", "true")
    clock = FakeClock()
    bridge, _ = _crystallized(clock)

    with pytest.raises(PublishWindowClosedError):
        bridge.open_window(opened_by="operator", ttl=timedelta(seconds=2))

    assert bridge._window is None
    assert any(entry["status"] == "disabled" for entry in bridge.emission_log())


def test_replay_attempts_fail_property() -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    bridge.emit(artifact, platform="alpha")

    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    for _ in range(3):
        with pytest.raises(ExpressionReplayError):
            bridge.emit(artifact, platform="alpha")


def test_restart_blocks_replay_via_fingerprint_store() -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    bridge.emit(artifact, platform="alpha")

    restarted = ExpressionBridge(now=clock.now)
    restarted.arm(reason="test")
    restarted.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    with pytest.raises(ExpressionReplayError):
        restarted.emit(artifact, platform="beta")


def test_concurrent_emissions_race_is_guarded(monkeypatch) -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))

    results: List[str] = []

    def _attempt_emit() -> None:
        try:
            bridge.emit(artifact, platform="alpha")
            results.append("success")
        except Exception as exc:  # noqa: BLE001
            results.append(exc.__class__.__name__)

    threads = [Thread(target=_attempt_emit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("success") == 1
    assert len(results) == 2


def _emit_in_subprocess(artifact: ExpressionArtifact, ttl_seconds: int) -> str:
    clock = FakeClock()
    bridge = ExpressionBridge(now=clock.now)
    bridge.arm(reason="test")
    bridge.open_window(opened_by="fork", ttl=timedelta(seconds=ttl_seconds))
    try:
        bridge.emit(artifact, platform="forked")
        return "success"
    except Exception as exc:  # noqa: BLE001
        return exc.__class__.__name__


def test_forked_processes_cannot_replay(monkeypatch) -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.open_window(opened_by="auditor", ttl=timedelta(seconds=5))
    bridge.emit(artifact, platform="alpha")

    with multiprocessing.get_context("fork").Pool(2) as pool:
        results = pool.starmap(_emit_in_subprocess, [(artifact, 5), (artifact, 5)])

    assert results.count("success") == 0
    assert all(result in {"ExpressionReplayError", "PublishWindowClosedError"} for result in results)


def test_cold_start_silence_and_autopsy_compression() -> None:
    bridge = ExpressionBridge()
    assert bridge._window is None
    assert bridge.emission_log() == []
    assert bridge.autopsies() == []

    artifact = ExpressionArtifact(
        content="quiet seed",
        epistemic_basis="manual",
        confidence_band="stable",
        contradiction_status=False,
        timestamp=datetime.now(timezone.utc),
        day_hash="seed",
        source_draft_id="draft-id",
    )
    for _ in range(50):
        bridge.discard(artifact)

    assert len(bridge.autopsies()) <= 32
    assert bridge.autopsies()[-1]["discarded_count"] >= 1


def test_autopsies_do_not_generate_intents() -> None:
    clock = FakeClock()
    bridge, artifact = _crystallized(clock)
    bridge.discard(artifact)
    autopsy = bridge.autopsies()[0]

    assert autopsy["intent_valid"] is True
    assert autopsy["state_influence"] == {"curiosity": False, "synthesis": False, "belief": False}
