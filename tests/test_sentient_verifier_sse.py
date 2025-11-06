from __future__ import annotations

import importlib
import json
import queue
import sys
import types

import pytest


@pytest.fixture()
def relay_app_module(monkeypatch):
    monkeypatch.setenv("CONSOLE_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")

    psutil_stub = types.SimpleNamespace(
        net_io_counters=lambda: types.SimpleNamespace(bytes_sent=0, bytes_recv=0),
        disk_io_counters=lambda: types.SimpleNamespace(read_bytes=0, write_bytes=0),
        cpu_percent=lambda: 0.0,
        virtual_memory=lambda: types.SimpleNamespace(percent=0.0),
        disk_usage=lambda _path: types.SimpleNamespace(percent=0.0),
    )
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)

    fake_sentientscript = types.ModuleType("sentientscript")

    class _FakeResult:
        def __init__(self) -> None:
            self.run_id = "test"
            self.fingerprint = "sha256:test"
            self.outputs: dict[str, object] = {}

    class _FakeInterpreter:
        def __init__(self) -> None:
            self.history: list[dict[str, object]] = []
            self.signer = types.SimpleNamespace(sign=lambda script: script, verify=lambda script: True)

        def build_shadow(self, **_kwargs):  # type: ignore[no-untyped-def]
            return {}

        def load_script(self, payload):  # type: ignore[no-untyped-def]
            return dict(payload)

        def execute(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return _FakeResult()

    fake_sentientscript.ScriptExecutionError = RuntimeError
    fake_sentientscript.SentientScriptInterpreter = _FakeInterpreter
    fake_sentientscript.list_script_history = lambda *_, **__: []
    fake_sentientscript.load_safety_shadow = lambda *_, **__: None
    monkeypatch.setitem(sys.modules, "sentientscript", fake_sentientscript)

    import flask_stub

    original_request_init = flask_stub.Request.__init__

    def _request_init(self, json_data=None, headers=None):  # type: ignore[no-untyped-def]
        original_request_init(self, json_data, headers)
        self.remote_addr = "127.0.0.1"

    monkeypatch.setattr(flask_stub.Request, "__init__", _request_init)

    original_get_json = flask_stub.Response.get_json

    def _response_get_json(self):  # type: ignore[no-untyped-def]
        if isinstance(self.data, flask_stub.Response):
            return self.data.get_json()
        if isinstance(self.data, (str, bytes, bytearray)):
            return json.loads(self.data)
        return original_get_json(self)

    monkeypatch.setattr(flask_stub.Response, "get_json", _response_get_json)

    original_test_client = flask_stub.Flask.test_client

    def _test_client(app):  # type: ignore[no-untyped-def]
        class Client:
            def post(self, path, json=None, headers=None):  # type: ignore[no-untyped-def]
                req = flask_stub.Request(json, headers)
                flask_stub.request = req
                view = app.view_funcs.get(path)
                args: tuple = ()
                if view is None:
                    for route, func in app.view_funcs.items():
                        if "<" in route and ">" in route:
                            prefix, remainder = route.split("<", 1)
                            param, suffix = remainder.split(">", 1)
                            if path.startswith(prefix) and path.endswith(suffix):
                                value = path[len(prefix): len(path) - len(suffix) if suffix else None]
                                req.view_args = {param: value}
                                view = func
                                args = (value,)
                                break
                if view is None:
                    raise KeyError(path)
                view.__globals__["request"] = req
                rv = view(*args)
                if isinstance(rv, tuple):
                    data, status = rv
                    if isinstance(data, dict):
                        data = json.dumps(data)
                    return flask_stub.Response(data, status)
                if isinstance(rv, dict):
                    return flask_stub.Response(json.dumps(rv), 200)
                if isinstance(rv, flask_stub.Response) or hasattr(rv, "status_code"):
                    return rv
                return flask_stub.Response(rv, 200)

        return Client()

    monkeypatch.setattr(flask_stub.Flask, "test_client", _test_client)
    sys.modules.pop("relay_app", None)
    module = importlib.import_module("relay_app")
    if hasattr(module.app, "config"):
        module.app.config.update(TESTING=True)
    module._VERIFIER_RATE_LIMIT.reset()  # type: ignore[attr-defined]
    return module


def _drain_events(subscriber: "queue.Queue", attempts: int = 10) -> list[dict]:
    events: list[dict] = []
    for _ in range(max(1, attempts)):
        try:
            events.append(subscriber.get(timeout=0.5))
        except queue.Empty:
            break
    return events


def test_verifier_update_event_broadcasts_to_console(relay_app_module):
    relay_app = relay_app_module
    subscriber = relay_app._ADMIN_EVENTS.subscribe()  # type: ignore[attr-defined]
    try:
        client = relay_app.app.test_client()
        response = client.post(
            "/admin/verify/submit",
            json={"bundle": {"script": {"steps": []}, "env": {}, "claimed_run": {}}},
            headers={"X-Node-Token": "token"},
        )
        assert response.status_code == 200
        events = _drain_events(subscriber)
        update_events = [event for event in events if event.get("event") == "verifier_update"]
        assert update_events, f"expected verifier_update event, saw: {events}"
        payload = update_events[-1].get("data") or {}
        assert payload.get("verdict") == "VERIFIED_OK"
        assert payload.get("job_id")
        assert payload.get("timestamp")
    finally:
        relay_app._ADMIN_EVENTS.unsubscribe(subscriber)  # type: ignore[attr-defined]


def test_console_receives_live_verdict(relay_app_module):
    relay_app = relay_app_module
    subscriber = relay_app._ADMIN_EVENTS.subscribe()  # type: ignore[attr-defined]
    try:
        script = {"steps": [{"action": "const", "value": 7}]}
        client = relay_app.app.test_client()
        response = client.post(
            "/admin/verify/submit",
            json={"bundle": {"script": script, "env": {}, "claimed_run": {}}},
            headers={"X-Node-Token": "token"},
        )
        assert response.status_code == 200
        response_payload = response.get_json()
        assert response_payload
        events = _drain_events(subscriber)
        update = next((event for event in events if event.get("event") == "verifier_update"), None)
        assert update is not None, f"missing verifier_update in {events}"
        payload = update.get("data") or {}
        assert payload.get("job_id") == response_payload.get("job_id")
        assert payload.get("script_hash")
        assert payload.get("verdict") == "VERIFIED_OK"
        assert "score" in payload
    finally:
        relay_app._ADMIN_EVENTS.unsubscribe(subscriber)  # type: ignore[attr-defined]
