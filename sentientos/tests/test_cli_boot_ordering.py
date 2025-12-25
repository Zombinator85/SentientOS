from __future__ import annotations

import pytest

from sentientos import __main__ as sentientos_main


def test_help_runs_without_privilege_gate(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def _deny() -> None:
        raise AssertionError("Privilege gate should not be invoked for --help.")

    monkeypatch.setattr(sentientos_main, "_enforce_privileges", _deny)
    with pytest.raises(SystemExit) as excinfo:
        sentientos_main.main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()


def test_status_runs_without_privilege_gate(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def _deny() -> None:
        raise AssertionError("Privilege gate should not be invoked for status.")

    monkeypatch.setattr(sentientos_main, "_enforce_privileges", _deny)
    sentientos_main.main(["status"])
    captured = capsys.readouterr()
    assert "Status:" in captured.out


def test_doctor_runs_without_privilege_gate(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def _deny() -> None:
        raise AssertionError("Privilege gate should not be invoked for doctor.")

    monkeypatch.setattr(sentientos_main, "_enforce_privileges", _deny)
    sentientos_main.main(["doctor"])
    captured = capsys.readouterr()
    assert "Doctor:" in captured.out


def test_actionable_command_requires_privileges(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _deny() -> None:
        calls.append("denied")
        raise SystemExit("denied")

    monkeypatch.setattr(sentientos_main, "_enforce_privileges", _deny)
    with pytest.raises(SystemExit, match="denied"):
        sentientos_main.main(["dashboard"])
    assert calls == ["denied"]
