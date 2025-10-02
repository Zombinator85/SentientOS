from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sentientos.boot_chronicler import ChangeRecall, CeremonyLink, Chronicler, MemoryMark
from sentientos.change_narrator import ChangeCollector
from sentientos.codex_healer import Anomaly, RecoveryLedger


class DummyEmitter:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def emit(self, message: str, *, level: str = "info") -> None:
        self.messages.append((level, message))


@pytest.fixture()
def collector(tmp_path):
    ledger = RecoveryLedger()
    state_path = tmp_path / "boot_state.json"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    collector = ChangeCollector(ledger=ledger, repo_path=repo_path, state_path=state_path)
    return collector, ledger


def _build_link(collector: ChangeCollector) -> tuple[CeremonyLink, DummyEmitter]:
    emitter = DummyEmitter()
    recall = ChangeRecall(collector)
    chronicler = Chronicler()
    memory = MemoryMark(collector)
    link = CeremonyLink(emitter, recall, chronicler, memory)
    return link, emitter


def test_boot_retrospective_skips_when_no_changes(collector: tuple[ChangeCollector, RecoveryLedger]) -> None:
    collector_obj, ledger = collector
    link, emitter = _build_link(collector_obj)
    link.narrate(now=datetime.now(timezone.utc))
    assert emitter.messages == []


def test_boot_retrospective_composes_single_passage(collector: tuple[ChangeCollector, RecoveryLedger]) -> None:
    collector_obj, ledger = collector
    link, emitter = _build_link(collector_obj)
    ledger.log("Rebuilt LocalModel wrapper", anomaly=Anomaly(kind="codex", subject="LocalModel"))
    ledger.log(
        "Forged IntegrityDaemon check",
        anomaly=Anomaly(kind="integrity", subject="IntegrityDaemon"),
    )

    moment = datetime.now(timezone.utc) + timedelta(seconds=1)
    link.narrate(now=moment)

    assert len(emitter.messages) == 1
    level, message = emitter.messages[0]
    assert level == "info"
    assert message.lower().startswith("allen, since my last awakening")
    assert "\n" not in message
    assert "•" not in message


def test_boot_retrospective_does_not_repeat_changes(collector: tuple[ChangeCollector, RecoveryLedger]) -> None:
    collector_obj, ledger = collector
    link, emitter = _build_link(collector_obj)
    ledger.log("Calibrated ceremony", anomaly=Anomaly(kind="ritual", subject="Boot"))

    first_moment = datetime.now(timezone.utc) + timedelta(seconds=1)
    link.narrate(now=first_moment)
    assert len(emitter.messages) == 1

    second_moment = first_moment + timedelta(seconds=1)
    link.narrate(now=second_moment)
    assert len(emitter.messages) == 1


def test_boot_retrospective_ignores_recall_failures(collector: tuple[ChangeCollector, RecoveryLedger]) -> None:
    collector_obj, ledger = collector
    emitter = DummyEmitter()

    class ExplodingRecall:
        def gather(self, *, now=None):  # type: ignore[no-untyped-def]
            raise RuntimeError("ledger offline")

    memory = MemoryMark(collector_obj)
    link = CeremonyLink(emitter, ExplodingRecall(), Chronicler(), memory)

    link.narrate(now=datetime.now(timezone.utc))

    assert emitter.messages == []
