from __future__ import annotations

import threading
from pathlib import Path

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_pair_entrypoint import run_pair
from tests.test_gaming_companion_pair_supervisor import _deployment
from tests.test_gaming_companion_role_entrypoint import _manifest

pytestmark = pytest.mark.no_legacy_skip


def test_pair_launch_authority_precedes_provider_and_platform_custody(tmp_path: Path) -> None:
    events: list[str] = []
    pair, _core, _edge = _deployment(tmp_path, events)
    calls: list[str] = []

    with pytest.raises(CompanionBridgeError, match="pair_launch_authority_denied"):
        run_pair(manifest=_manifest(), pair_provider=lambda _value: calls.append("provider") or pair,
            launch_authorizer=lambda _value: calls.append("authorize") and False,
            stop_event=threading.Event(), system_name="Windows")

    assert calls == ["authorize"]
    assert events == []


def test_pair_entrypoint_starts_both_roles_and_closes_on_shutdown(tmp_path: Path) -> None:
    events: list[str] = []
    pair, core, edge = _deployment(tmp_path, events)
    calls: list[str] = []
    stop = threading.Event()
    stop.set()

    result = run_pair(manifest=_manifest(), pair_provider=lambda _value: calls.append("provider") or pair,
        launch_authorizer=lambda _value: calls.append("authorize") or True,
        stop_event=stop, poll_interval_seconds=0.05, system_name="Windows")

    assert result == 0
    assert calls == ["authorize", "provider"]
    assert events.index("spawn:wsl_core") < events.index("spawn:windows_edge")
    assert events.index("terminate:windows_edge") < events.index("terminate:wsl_core")
    assert core.status().state == "stopped" and edge.status().state == "stopped"


def test_pair_entrypoint_rejects_non_windows_before_authority_or_provider() -> None:
    calls: list[str] = []
    with pytest.raises(CompanionBridgeError, match="windows_host_required"):
        run_pair(manifest=_manifest(),
            pair_provider=lambda _value: calls.append("provider"),
            launch_authorizer=lambda _value: calls.append("authorize") or True,
            stop_event=threading.Event(), system_name="Linux")
    assert calls == []


def test_pair_provider_must_return_exact_pair_supervisor() -> None:
    with pytest.raises(CompanionBridgeError, match="supervisor_type_mismatch"):
        run_pair(manifest=_manifest(), pair_provider=lambda _value: object(),
            launch_authorizer=lambda _value: True, stop_event=threading.Event(),
            system_name="Windows")
