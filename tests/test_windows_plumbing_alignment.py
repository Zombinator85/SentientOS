from importlib import reload
from pathlib import Path
from types import SimpleNamespace

import cathedral_launcher
import relay_server


def test_relay_health_status_reports_expected_fields(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    reload(relay_server)
    monkeypatch.setattr(
        relay_server,
        "CONFIG",
        relay_server.RelayConfig(
            relay_host="127.0.0.1",
            relay_port=4020,
            llama_host="127.0.0.1",
            llama_port=8000,
            llama_retries=1,
            llama_retry_delay=0,
        ),
    )
    monkeypatch.setattr(relay_server, "BACKEND_READY", True)
    monkeypatch.setattr(relay_server, "MODEL", None)
    monkeypatch.setattr(relay_server, "START_TIME", relay_server.time.time() - 2)

    from fastapi.testclient import TestClient

    client = TestClient(relay_server.app)

    status_data = client.get("/health/status").json()
    base_data = client.get("/health").json()

    assert status_data == base_data
    assert status_data["status"] == "ready"
    assert status_data["relay_host"] == "127.0.0.1"
    assert status_data["relay_port"] == 4020
    assert status_data["uptime_s"] >= 0


def test_relay_defaults_to_local_binding(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    monkeypatch.delenv("RELAY_HOST", raising=False)
    reload(relay_server)
    assert relay_server.RelayConfig().relay_host == "127.0.0.1"


def test_cathedral_attach_mode_skips_relay_launch(monkeypatch, tmp_path):
    env_file = tmp_path / "env"
    env_file.write_text("")
    monkeypatch.setattr(cathedral_launcher, "ensure_env_file", lambda: env_file)
    monkeypatch.setattr(cathedral_launcher, "ensure_log_dir", lambda: tmp_path)
    monkeypatch.setattr(cathedral_launcher, "check_updates", lambda: None)
    monkeypatch.setattr(cathedral_launcher, "check_python_version", lambda: True)
    monkeypatch.setattr(cathedral_launcher, "ensure_venv_active", lambda: True)
    monkeypatch.setattr(cathedral_launcher, "ensure_pip", lambda: None)
    monkeypatch.setattr(cathedral_launcher, "ensure_virtualenv", lambda: None)
    monkeypatch.setattr(cathedral_launcher, "install_requirements", lambda: None)
    monkeypatch.setattr(cathedral_launcher, "ensure_required_modules", lambda: True)
    monkeypatch.setattr(cathedral_launcher, "check_gpu", lambda: (True, True))
    monkeypatch.setattr(cathedral_launcher, "detect_avx", lambda: True)
    monkeypatch.setattr(cathedral_launcher, "save_hardware_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(cathedral_launcher, "prompt_cloud_inference", lambda *args, **kwargs: None)
    monkeypatch.setattr(cathedral_launcher, "HARDWARE_PROFILE", tmp_path / "hardware.json")
    monkeypatch.setattr(cathedral_launcher, "MODEL_PREFERENCE", tmp_path / "model_preference.txt")

    launches: list[list[str]] = []

    def fake_launch(cmd, stdout=None, env=None):
        launches.append(cmd)

        class _Proc:
            def terminate(self) -> None:
                return None

        return _Proc()

    monkeypatch.setattr(cathedral_launcher, "launch_background", fake_launch)
    monkeypatch.setattr(cathedral_launcher, "wait_for_relay_health", lambda *args, **kwargs: True)
    monkeypatch.setattr(cathedral_launcher, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(cathedral_launcher, "webbrowser", SimpleNamespace(open=lambda *args, **kwargs: None))

    exit_code = cathedral_launcher.main(
        [
            "--relay-port",
            "4100",
            "--webui-port",
            "8600",
            "--model-port",
            "8000",
            "--relay-host",
            "127.0.0.1",
            "--attach-relay",
        ]
    )

    assert exit_code == cathedral_launcher.EXIT_OK
    assert launches == []


def test_windows_scripts_reference_unified_ports():
    start = Path("Start-All.ps1").read_text(encoding="utf-8")
    stop = Path("Stop-All.ps1").read_text(encoding="utf-8")

    assert "--llama-port $LlamaPort" in start
    assert "/health/status" in start
    assert "/health/status" in stop
    assert "8000" in start
    assert "8000" in stop
    assert "/v1/health" not in start
    assert "/v1/health" not in stop
