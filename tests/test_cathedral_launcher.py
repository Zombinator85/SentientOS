"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cathedral_launcher as cl


def test_check_gpu(monkeypatch):
    # Simulate torch with GPU
    class Torch:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return True

    monkeypatch.setitem(sys.modules, "torch", Torch)
    importlib.reload(cl)
    assert cl.check_gpu()

    # Simulate torch without GPU
    class TorchNo:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return False

    monkeypatch.setitem(sys.modules, "torch", TorchNo)
    importlib.reload(cl)
    assert not cl.check_gpu()


def test_prompt_cloud_inference(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("EXAMPLE=1")
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    cl.prompt_cloud_inference(env)
    assert "MODEL_REMOTE_ONLY=1" in env.read_text()

    # second call should not prompt again
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(Exception("asked")))
    cl.prompt_cloud_inference(env)
    assert env.read_text().count("MODEL_REMOTE_ONLY") == 1


def test_prompt_cloud_inference_no(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("EXAMPLE=1")
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    cl.prompt_cloud_inference(env)
    assert "MODEL_REMOTE_ONLY=0" in env.read_text()


def test_check_llama_server(monkeypatch):
    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(cl.socket, "create_connection", lambda *a, **k: DummyConn())
    assert cl.check_llama_server()
    monkeypatch.setattr(
        cl.socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no route")),
    )
    assert not cl.check_llama_server()


def test_check_python_version(monkeypatch):
    vinfo = sys.version_info
    monkeypatch.setattr(sys, "version_info", (3, 10, 0))
    assert not cl.check_python_version()
    monkeypatch.setattr(sys, "version_info", vinfo)
    assert cl.check_python_version()


def test_env_file_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("EXAMPLE=1")
    env = cl.ensure_env_file()
    assert env.exists()
    assert env.read_text() == "EXAMPLE=1"


def test_log_dir_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = cl.ensure_log_dir()
    assert path.exists()


def test_log_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "launcher.log"
    monkeypatch.setattr(cl, "LOG_PATH", target)
    cl.log("hello")
    assert target.read_text().strip() == "hello"


def test_ensure_virtualenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "prefix", "/usr")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    called = {}

    def fake_create(path, *, with_pip=True):
        called["path"] = path
        called["with_pip"] = with_pip

    monkeypatch.setattr(cl.venv, "create", fake_create)
    cl.ensure_virtualenv()
    assert called["path"] == tmp_path / ".venv"
