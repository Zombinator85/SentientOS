from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_local_codex_foreman as foreman
from tests.maintenance_watchdog_implementation_fixtures import NOW, setup

pytestmark = pytest.mark.no_legacy_skip


def _commissioned(cfg: dict[str, object], activation: Path, content: bytes = b"{}") -> dict[str, object]:
    activation.write_bytes(content)
    value = dict(cfg)
    value.pop("config_digest", None)
    value.update(
        implementation_backend="commissioned_local",
        commissioned_local_activation=str(activation.resolve()),
        commissioned_local_activation_digest="sha256:" + hashlib.sha256(content).hexdigest(),
    )
    return watchdog.validate_config(value)


def _advance(cfg: dict[str, object], count: int) -> list[dict[str, object]]:
    return [watchdog.tick(cfg, evaluation_time=NOW) for _ in range(count)]


def test_commissioned_backend_missing_activation_blocks_without_codex(tmp_path, monkeypatch):
    cfg, _, _ = setup(tmp_path)
    cfg = _commissioned(cfg, tmp_path / "activation.json")
    Path(str(cfg["commissioned_local_activation"])).unlink()
    monkeypatch.setattr(foreman.LocalCodexDriver, "__init__", lambda self: pytest.fail("Codex fallback"))
    result = _advance(cfg, 4)[-1]
    assert result["status"] == "blocked"
    assert result["configured_backend"] == "commissioned_local"
    assert result["effect_result"]["failure_detail"] == "commissioned_local_activation_invalid"


def test_activation_digest_substitution_blocks_without_codex(tmp_path, monkeypatch):
    cfg, _, _ = setup(tmp_path)
    activation = tmp_path / "activation.json"
    cfg = _commissioned(cfg, activation)
    activation.write_text('{"substituted":true}')
    monkeypatch.setattr(foreman.LocalCodexDriver, "__init__", lambda self: pytest.fail("Codex fallback"))
    result = _advance(cfg, 4)[-1]
    assert result["status"] == "blocked"
    assert result["effect_result"]["failure_detail"] == "commissioned_local_activation_digest_mismatch"


def test_backend_and_exact_activation_survive_config_reload(tmp_path):
    cfg, _, _ = setup(tmp_path)
    activation = tmp_path / "activation.json"
    cfg = _commissioned(cfg, activation, b'{"exact":"identity-x"}')
    path = tmp_path / "watchdog.json"
    path.write_text(json.dumps(cfg, sort_keys=True))
    loaded = watchdog.load_config(path)
    assert loaded["implementation_backend"] == "commissioned_local"
    assert loaded["commissioned_local_activation"] == str(activation.resolve())
    assert loaded["commissioned_local_activation_digest"] == "sha256:" + hashlib.sha256(activation.read_bytes()).hexdigest()


def test_watchdog_injects_only_explicit_commissioned_driver(tmp_path, monkeypatch):
    cfg, roots, _ = setup(tmp_path)
    cfg = _commissioned(cfg, tmp_path / "activation.json")
    calls = {"commissioned": 0}

    class Driver:
        driver_id = "commissioned_local_model"

        def describe_driver(self):
            from sentientos import maintenance_commissioned_local_agent as agent
            return agent.CommissionedLocalDriver.__new__(agent.CommissionedLocalDriver).describe_driver()

        def prepare_session(self, request, session):
            return {"prepared": True}

    class Model:
        def close(self): pass

    def selected(config):
        calls["commissioned"] += 1
        return Driver(), Model()

    monkeypatch.setattr(watchdog, "_commissioned_driver", selected)
    monkeypatch.setattr(foreman.LocalCodexDriver, "__init__", lambda self: pytest.fail("Codex fallback"))
    result = _advance(cfg, 4)[-1]
    session = json.loads(next((roots["state"] / "maintenance_agent_sessions").glob("*.json")).read_text())
    assert result["status"] == "agent_session_ready"
    assert result["instantiated_backend"] == "commissioned_local"
    assert session["driver_descriptor"]["driver_kind"] == "commissioned_local"
    assert calls == {"commissioned": 1}


def test_local_codex_backend_forbids_activation_binding(tmp_path):
    cfg, _, _ = setup(tmp_path)
    cfg.pop("config_digest", None)
    cfg["commissioned_local_activation"] = "/tmp/activation.json"
    cfg["commissioned_local_activation_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="commissioned_local_activation_forbidden"):
        watchdog.validate_config(cfg)
