import importlib
import json
import sys
import types


def _reload_app(monkeypatch):
    monkeypatch.delenv("NODE_TOKEN", raising=False)
    psutil_stub = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)
    module = importlib.reload(importlib.import_module("relay_app"))
    return module


def test_manifest_served(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBUI_ENABLED", "1")
    module = _reload_app(monkeypatch)
    response = module.pwa_asset("manifest.webmanifest")
    status = getattr(response, "status_code", getattr(response, "status", 200))
    assert status == 200
    body = response.data if hasattr(response, "data") else response
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    manifest = json.loads(body)
    assert manifest["name"] == "SentientOS Console"
    worker = module.pwa_asset("service-worker.js")
    worker_status = getattr(worker, "status_code", getattr(worker, "status", 200))
    assert worker_status == 200
    worker_body = worker.data if hasattr(worker, "data") else worker
    if isinstance(worker_body, str):
        worker_body = worker_body.encode("utf-8")
    assert b"sentientos-pwa-v1" in worker_body
