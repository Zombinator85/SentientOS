from __future__ import annotations

import importlib
import json
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


def _submit_bundle(relay_app, client, bundle):
    response = client.post(
        "/admin/verify/submit",
        json={"bundle": bundle},
        headers={"X-Node-Token": "token"},
    )
    assert response.status_code == 200
    return response.get_json()


def test_replay_endpoint_reproduces_identical_verdict(relay_app_module):
    relay_app = relay_app_module
    client = relay_app.app.test_client()
    script = {"steps": [{"action": "const", "value": 3}]}
    bundle = {"script": script, "env": {}, "claimed_run": {}}
    initial = _submit_bundle(relay_app, client, bundle)
    replay_response = client.post(
        f"/admin/verify/replay/{initial['job_id']}",
        headers={"X-Node-Token": "token"},
    )
    assert replay_response.status_code == 200
    replay_payload = replay_response.get_json()
    assert replay_payload["verdict"] == initial["verdict"] == "VERIFIED_OK"
    assert replay_payload["job_id"] != initial["job_id"]


def test_rate_limit_blocks_excessive_submissions(relay_app_module):
    relay_app = relay_app_module
    original = relay_app._VERIFIER_RATE_LIMIT  # type: ignore[attr-defined]
    relay_app._VERIFIER_RATE_LIMIT = relay_app._RateLimiter(limit=2, window_seconds=60)  # type: ignore[attr-defined]
    try:
        client = relay_app.app.test_client()
        bundle = {"script": {"steps": []}, "env": {}, "claimed_run": {}}
        _submit_bundle(relay_app, client, bundle)
        _submit_bundle(relay_app, client, bundle)
        third = client.post(
            "/admin/verify/submit",
            json={"bundle": bundle},
            headers={"X-Node-Token": "token"},
        )
        assert third.status_code == 429
        payload = third.get_json()
        assert payload["error"] == "rate_limited"
    finally:
        relay_app._VERIFIER_RATE_LIMIT = original  # type: ignore[attr-defined]


def test_proof_trace_evaluations_pass_and_fail_correctly(relay_app_module):
    relay_app = relay_app_module
    script = {
        "steps": [
            {
                "action": "echo",
                "value": 1,
                "proofs": [
                    {"pre": '"value" not in state', "post": 'state["value"] == 1'},
                ],
            },
            {
                "action": "const",
                "value": -1,
                "proofs": [
                    {"pre": 'state["value"] == 1', "post": 'result["value"] > 0'},
                ],
            },
        ]
    }
    report = relay_app._SENTIENT_VERIFIER.verify_bundle({"script": script, "env": {}, "claimed_run": {}})
    assert report.proof_counts["pass"] == 1
    assert report.proof_counts["fail"] == 1
    assert report.proof_counts.get("error", 0) == 0
    statuses = [trace.status for trace in report.proofs]
    assert statuses == ["PASS", "FAIL"]
    assert report.proof_hash


def test_suspended_node_submission_rejected(relay_app_module):
    relay_app = relay_app_module
    client = relay_app.app.test_client()
    relay_app.registry.register_or_update(  # type: ignore[attr-defined]
        "omega",
        "127.0.0.1",
        capabilities={},
    )
    record = relay_app.registry.get("omega")  # type: ignore[attr-defined]
    assert record is not None
    record.trust_score = -5
    response = client.post(
        "/admin/verify/submit",
        json={"bundle": {"script": {"steps": []}, "env": {}, "claimed_run": {}}},
        headers={"X-Node-Token": "token", "X-Node-Id": "omega"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "node_suspended"
