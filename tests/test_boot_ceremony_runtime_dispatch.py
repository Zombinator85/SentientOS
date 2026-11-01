from __future__ import annotations

import pytest

from sentientos import boot_ceremony
from sentientos.boot_ceremony import BootAnnouncer, BootCeremonyError, CeremonialScript, EventEmitter

pytestmark = pytest.mark.no_legacy_skip


def test_boot_healer_uses_runtime_mediated_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(boot_ceremony, "runtime_monitor", lambda: calls.append("monitor"))

    CeremonialScript._wake_healer()

    assert calls == ["monitor"]


def test_boot_forge_uses_runtime_mediated_proposal_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(boot_ceremony, "runtime_expand", lambda: calls.append("proposal"))

    CeremonialScript._prime_forge()

    assert calls == ["proposal"]


def test_failed_boot_step_dispatches_through_runtime_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(boot_ceremony, "runtime_monitor", lambda: calls.append("monitor"))
    script = CeremonialScript(BootAnnouncer(EventEmitter()))

    with pytest.raises(BootCeremonyError):
        script._execute_step(
            boot_ceremony.CeremonialStep(
                announcement="test failure",
                success="unexpected success",
                action=lambda: (_ for _ in ()).throw(RuntimeError("expected")),
            )
        )

    assert calls == ["monitor"]
