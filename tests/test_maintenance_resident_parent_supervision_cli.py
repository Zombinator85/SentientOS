from __future__ import annotations

import pytest

from sentientos import maintenance_resident_parent_supervision as parent
from sentientos import maintenance_initial_posix_resident_commissioning as commissioning


def test_parent_entrypoint_requires_explicit_config(monkeypatch) -> None:
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("configuration loading must not run without an explicit path")

    monkeypatch.setattr(commissioning, "verify_commissioned_resident_config", forbidden)
    with pytest.raises(SystemExit) as error:
        parent.main([])
    assert error.value.code == 2
    assert called is False


def test_parent_entrypoint_rejects_relative_config_before_loading(monkeypatch) -> None:
    loaded = False

    def forbidden(*args, **kwargs):
        nonlocal loaded
        loaded = True
        raise AssertionError("relative paths are not accepted")

    monkeypatch.setattr(parent.resident, "load_config", forbidden)
    assert parent.main(["--config", "resident.json"]) == 2
    assert loaded is False
