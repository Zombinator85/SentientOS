from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Deque, List

import pytest

from codex import LedgerInterface, PatchStorage, RewriteDashboard, ScopedRewriteEngine


class DummyLedger(LedgerInterface):
    def __init__(self, verdicts: List[bool]) -> None:
        self._verdicts: Deque[bool] = deque(verdicts)
        self.recorded: List[str] = []

    def verify_patch(self, patch):  # type: ignore[override]
        self.recorded.append(patch.patch_id)
        if not self._verdicts:
            raise RuntimeError("Ledger ran out of verdicts")
        return self._verdicts.popleft()


@dataclass
class ManualClock:
    moment: datetime

    def tick(self, delta: timedelta) -> None:
        self.moment += delta

    def now(self) -> datetime:
        return self.moment


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(moment=datetime(2025, 1, 1, tzinfo=timezone.utc))


def _engine(tmp_path: Path, ledger: LedgerInterface, clock: ManualClock, cooldown: int = 60) -> ScopedRewriteEngine:
    glow_dir = tmp_path / "glow" / "patches"
    quarantine_dir = tmp_path / "daemon" / "quarantine"
    storage = PatchStorage(glow_dir, quarantine_dir)
    return ScopedRewriteEngine(ledger, storage=storage, cooldown=timedelta(seconds=cooldown), now=clock.now)


def test_ledger_gating_and_patch_reversibility(tmp_path: Path, clock: ManualClock) -> None:
    target = tmp_path / "daemon_module.py"
    target.write_text("value = 1\n", encoding="utf-8")

    ledger = DummyLedger([True, False])
    engine = _engine(tmp_path, ledger, clock, cooldown=0)

    approved_patch = engine.request_rewrite(
        "HealingDaemon",
        target,
        "value = 2\n",
        reason="heal drift",
        confidence=0.9,
        urgency="high",
    )

    applied = engine.process_pending()
    assert applied and applied[0].patch_id == approved_patch.patch_id
    assert target.read_text(encoding="utf-8") == "value = 2\n"

    original_path = tmp_path / "glow" / "patches" / approved_patch.patch_id / "original.txt"
    modified_path = tmp_path / "glow" / "patches" / approved_patch.patch_id / "modified.txt"
    assert original_path.read_text(encoding="utf-8") == "value = 1\n"
    assert modified_path.read_text(encoding="utf-8") == "value = 2\n"

    engine.revert_patch(approved_patch.patch_id)
    assert target.read_text(encoding="utf-8") == "value = 1\n"

    denied_patch = engine.request_rewrite(
        "HealingDaemon",
        target,
        "value = 3\n",
        reason="overheal",
        confidence=0.4,
        urgency="medium",
    )
    engine.process_pending()

    quarantine_dir = tmp_path / "daemon" / "quarantine" / denied_patch.patch_id
    assert quarantine_dir.exists(), "Denied patch should move to quarantine"
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_backlog_ordering_and_cooldown(tmp_path: Path, clock: ManualClock) -> None:
    target = tmp_path / "daemon_module.py"
    target.write_text("value = 0\n", encoding="utf-8")

    ledger = DummyLedger([True, True, True])
    engine = _engine(tmp_path, ledger, clock, cooldown=120)

    low_patch = engine.request_rewrite(
        "HealingDaemon",
        target,
        "value = 1\n",
        reason="minor tune",
        confidence=0.3,
        urgency="low",
    )
    mid_patch = engine.request_rewrite(
        "HealingDaemon",
        target,
        "value = 2\n",
        reason="mid tune",
        confidence=0.8,
        urgency="medium",
    )
    high_patch = engine.request_rewrite(
        "HealingDaemon",
        target,
        "value = 3\n",
        reason="critical fix",
        confidence=0.5,
        urgency="high",
    )

    applied = engine.process_pending()
    assert applied and applied[0].patch_id == high_patch.patch_id
    assert target.read_text(encoding="utf-8") == "value = 3\n"

    backlog_ids = [patch.patch_id for patch in engine.backlog("HealingDaemon")]
    assert backlog_ids == [mid_patch.patch_id, low_patch.patch_id]

    clock.tick(timedelta(seconds=120))
    engine.process_pending()
    assert target.read_text(encoding="utf-8") == "value = 2\n"

    clock.tick(timedelta(seconds=120))
    engine.process_pending()
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_dashboard_visibility(tmp_path: Path, clock: ManualClock) -> None:
    target = tmp_path / "daemon_module.py"
    target.write_text("value = 5\n", encoding="utf-8")

    ledger = DummyLedger([True])
    engine = _engine(tmp_path, ledger, clock, cooldown=0)

    patch = engine.request_rewrite(
        "HealingDaemon",
        target,
        "value = 8\n",
        reason="operator command",
        confidence=0.95,
        urgency="medium",
        metadata={"glow": "self"},
    )
    engine.process_pending()

    storage = PatchStorage(tmp_path / "glow" / "patches", tmp_path / "daemon" / "quarantine")
    dashboard = RewriteDashboard(storage)
    rows = dashboard.rows()
    assert rows, "dashboard should surface at least one patch"

    row = next(entry for entry in rows if entry["patch_id"] == patch.patch_id)
    assert row["reason"] == "operator command"
    assert "@@" in row["diff_summary"]
    assert pytest.approx(row["confidence"], rel=1e-3) == 0.95
    assert row["actions"]["approve"] is False
    assert row["actions"]["revert"] is True
    assert row["override"] is False
