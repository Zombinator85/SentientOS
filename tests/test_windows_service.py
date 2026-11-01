from __future__ import annotations

import pytest

from sentientos import windows_service

pytestmark = pytest.mark.no_legacy_skip


def test_windows_service_fails_clearly_when_pywin32_is_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(windows_service, "win32serviceutil", None)
    monkeypatch.setattr(windows_service, "win32service", None)
    monkeypatch.setattr(windows_service, "win32event", None)

    with pytest.raises(RuntimeError, match="pywin32 is required"):
        windows_service.SentientOSService()
    with pytest.raises(RuntimeError, match="pywin32 is required"):
        windows_service.install_service()
    with pytest.raises(RuntimeError, match="pywin32 is required"):
        windows_service.remove_service()
