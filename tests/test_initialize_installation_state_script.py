from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import initialize_installation_state
from sentientos.installation_state import InstallationStateRegistry


pytestmark = pytest.mark.no_legacy_skip


def test_initializer_uses_system_registry_and_independently_reopens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = InstallationStateRegistry._for_testing(tmp_path / "machine-state")
    calls: list[bool] = []
    original_open = InstallationStateRegistry.open

    def observed_open(self: InstallationStateRegistry, identity: object, *, create: bool = False):
        calls.append(create)
        return original_open(self, identity, create=create)  # type: ignore[arg-type]

    monkeypatch.setattr(InstallationStateRegistry, "open", observed_open)
    monkeypatch.setattr(InstallationStateRegistry, "system", classmethod(lambda cls: registry))

    assert initialize_installation_state.main(["--installation-identity", "PRIMARY"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "authority_granted": False,
        "canonical_state_root": str(tmp_path / "machine-state/installations/primary/state"),
        "installation_identity": "primary",
        "status": "installation_state_initialized",
    }
    assert calls == [True, False]


def test_initializer_rejects_invalid_identity_without_opening_registry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        InstallationStateRegistry,
        "system",
        classmethod(lambda cls: pytest.fail("registry must not open")),
    )
    assert initialize_installation_state.main(["--installation-identity", "../other"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "reason_code": "invalid_installation_identity",
        "status": "blocked",
    }


def test_initializer_has_no_alternate_state_root_argument() -> None:
    with pytest.raises(SystemExit) as exc:
        initialize_installation_state.main([
            "--installation-identity", "primary", "--state-root", "/tmp/substitute"
        ])
    assert exc.value.code == 2
