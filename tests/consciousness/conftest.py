import pytest

from sentientos.daemons import pulse_bus


@pytest.fixture(autouse=True)
def isolated_consciousness_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_INTROSPECTION_LOG", str(tmp_path / "daemon" / "logs" / "introspection.jsonl"))
    monkeypatch.setenv("PULSE_HISTORY_ROOT", str(tmp_path / "pulse_history"))
    pulse_bus.reset()
    yield tmp_path
    pulse_bus.reset()
