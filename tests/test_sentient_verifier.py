from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from node_registry import NodeRegistry
from sentient_verifier import SentientVerifier
from verifier_store import VerifierStore


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _script_hash(script: dict[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(script).encode("utf-8")).hexdigest()


def _sign_run_log(script_hash: str, run_log: dict[str, object], signing_key: SigningKey) -> str:
    payload = dict(run_log)
    payload.pop("signature", None)
    payload["script_hash"] = script_hash
    message = _canonical_json(payload).encode("utf-8")
    return base64.b64encode(signing_key.sign(message).signature).decode("ascii")


def _make_registry(tmp_path: Path) -> NodeRegistry:
    return NodeRegistry(tmp_path / "nodes.json")


def _make_verifier(tmp_path: Path, registry: NodeRegistry) -> SentientVerifier:
    store = VerifierStore(tmp_path / "verify_store")
    return SentientVerifier(registry=registry, store=store)


def _register_node(registry: NodeRegistry, name: str, signing_key: SigningKey) -> str:
    fingerprint = hashlib.sha256(signing_key.verify_key.encode()).hexdigest()
    registry.register_or_update(
        name,
        "127.0.0.1",
        capabilities={"sentientscript_pubkey": base64.b64encode(signing_key.verify_key.encode()).decode("ascii")},
        trust_level="trusted",
        pubkey_fingerprint=fingerprint,
    )
    return fingerprint


def test_signature_mismatch_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    registry = _make_registry(tmp_path)
    verifier = _make_verifier(tmp_path, registry)
    signing_key = SigningKey.generate()
    fingerprint = _register_node(registry, "alpha", signing_key)

    script = {"steps": [{"action": "const", "value": 3}]}
    env = {"seed": 1, "clock_mode": "fixed", "start_time": 1700000000.0}
    claimed_steps = [{"i": 0, "action": "const", "result": {"value": 3}, "ts": 1700000000.0, "state_hash": "sha256:test"}]
    run_log = {
        "steps": claimed_steps,
        "final_state_hash": "sha256:test",
        "from_node": "alpha",
        "signer_fingerprint": fingerprint,
        "signature": base64.b64encode(b"invalid").decode("ascii"),
    }
    bundle = {"script": script, "claimed_run": run_log, "env": env}

    report = verifier.verify_bundle(bundle)
    assert report.verdict == "SIGNATURE_MISMATCH"


def test_deterministic_replay_equal_state_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    registry = _make_registry(tmp_path)
    verifier = _make_verifier(tmp_path, registry)
    signing_key = SigningKey.generate()
    fingerprint = _register_node(registry, "alpha", signing_key)

    script = {"steps": [{"action": "add", "operands": [1, 2, 3]}]}
    env = {"seed": 123, "clock_mode": "fixed", "start_time": 1111.0}
    replay = verifier._replay_engine(script, env)  # type: ignore[attr-defined]
    script_hash = _script_hash(script)
    run_log = {
        "steps": replay["steps"],
        "final_state_hash": replay["final_state_hash"],
        "from_node": "alpha",
        "signer_fingerprint": fingerprint,
    }
    run_log["signature"] = _sign_run_log(script_hash, run_log, signing_key)

    bundle = {"script": script, "claimed_run": run_log, "env": env}
    report = verifier.verify_bundle(bundle)
    assert report.verdict == "VERIFIED_OK"
    assert report.evidence["replay_final_state_hash"] == report.evidence["claimed_final_state_hash"]


def test_divergence_diff_points_to_step_and_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    registry = _make_registry(tmp_path)
    verifier = _make_verifier(tmp_path, registry)
    signing_key = SigningKey.generate()
    fingerprint = _register_node(registry, "alpha", signing_key)

    script = {"steps": [{"action": "const", "value": 5}, {"action": "multiply", "operands": [2, 3]}]}
    env = {"seed": 9, "clock_mode": "fixed", "start_time": 2222.0}
    replay = verifier._replay_engine(script, env)  # type: ignore[attr-defined]
    tampered_steps = list(replay["steps"])
    tampered_steps[1] = dict(tampered_steps[1])
    tampered_steps[1]["result"] = {"value": 5}
    script_hash = _script_hash(script)
    run_log = {
        "steps": tampered_steps,
        "final_state_hash": "sha256:tampered",
        "from_node": "alpha",
        "signer_fingerprint": fingerprint,
    }
    run_log["signature"] = _sign_run_log(script_hash, run_log, signing_key)

    bundle = {"script": script, "claimed_run": run_log, "env": env}
    report = verifier.verify_bundle(bundle)
    assert report.verdict == "DIVERGED"
    fields = {diff.field for diff in report.diffs}
    assert any(field.startswith("result") for field in fields)


def test_trust_score_changes_on_outcomes(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    registry.register_or_update("alpha", "127.0.0.1")
    assert registry.get_trust_score("alpha") == 0
    registry.apply_verification_outcome("alpha", "VERIFIED_OK")
    assert registry.get_trust_score("alpha") == 1
    registry.apply_verification_outcome("alpha", "DIVERGED")
    assert registry.get_trust_score("alpha") == -1
    registry.apply_verification_outcome("alpha", "SIGNATURE_MISMATCH")
    assert registry.get_trust_score("alpha") == -3
    registry.apply_verification_outcome("alpha", "DIVERGED")
    assert registry.get_trust_score("alpha") == -5
    record = registry.apply_verification_outcome("alpha", "VERIFIED_OK")
    assert record is not None and record.trust_level == "provisional"


def test_endpoints_submit_list_report_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "1")
    monkeypatch.setenv("NODE_TOKEN", "token")
    monkeypatch.setenv("PAIRING_RESET", "1")

    import sys
    import types

    psutil_stub = types.SimpleNamespace(
        net_io_counters=lambda: types.SimpleNamespace(bytes_sent=0, bytes_recv=0),
        disk_io_counters=lambda: types.SimpleNamespace(read_bytes=0, write_bytes=0),
        cpu_percent=lambda: 0.0,
        virtual_memory=lambda: types.SimpleNamespace(percent=0.0),
        disk_usage=lambda _path: types.SimpleNamespace(percent=0.0),
    )
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)

    fake_module = types.ModuleType("sentientscript")

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

    fake_module.ScriptExecutionError = RuntimeError
    fake_module.SentientScriptInterpreter = _FakeInterpreter
    fake_module.list_script_history = lambda *_, **__: []
    fake_module.load_safety_shadow = lambda *_, **__: None
    monkeypatch.setitem(sys.modules, "sentientscript", fake_module)

    import flask_stub

    original_request_init = flask_stub.Request.__init__

    def _request_init(self, json_data=None, headers=None):  # type: ignore[no-untyped-def]
        original_request_init(self, json_data, headers)
        self.remote_addr = "127.0.0.1"

    monkeypatch.setattr(flask_stub.Request, "__init__", _request_init)

    sys.modules.pop("relay_app", None)
    import relay_app
    if hasattr(relay_app.app, "config"):
        relay_app.app.config.update(TESTING=True)

    signing_key = SigningKey.generate()
    fingerprint = _register_node(relay_app.registry, "alpha", signing_key)

    script = {"steps": [{"action": "add", "operands": [10, 5]}]}
    env = {"seed": 5, "clock_mode": "fixed", "start_time": 3333.0}
    replay = relay_app._SENTIENT_VERIFIER._replay_engine(script, env)  # type: ignore[attr-defined]
    script_hash = _script_hash(script)
    run_log = {
        "steps": replay["steps"],
        "final_state_hash": replay["final_state_hash"],
        "from_node": "alpha",
        "signer_fingerprint": fingerprint,
    }
    run_log["signature"] = _sign_run_log(script_hash, run_log, signing_key)
    bundle = {"script": script, "claimed_run": run_log, "env": env}

    client = relay_app.app.test_client()
    response = client.post(
        "/admin/verify/submit",
        json={"bundle": bundle},
        headers={"X-Node-Token": "token"},
    )
    assert response.status_code == 200
    payload_response = response
    if hasattr(response, "data") and hasattr(response.data, "get_json"):
        payload_response = response.data
    payload = payload_response.get_json()
    assert payload and payload["verdict"] == "VERIFIED_OK"
    job_id = payload["job_id"]

    list_request = flask_stub.Request(headers={"X-Node-Token": "token"})
    list_request.remote_addr = "127.0.0.1"
    list_request.args = {"limit": "5"}
    relay_app.request = list_request  # type: ignore[attr-defined]
    listing = relay_app.admin_verify_list()
    listing_response = listing
    if hasattr(listing, "data") and hasattr(listing.data, "get_json"):
        listing_response = listing.data
    reports = listing_response.get_json().get("reports", [])
    assert any(report["job_id"] == job_id for report in reports)

    report_request = flask_stub.Request(headers={"X-Node-Token": "token"})
    report_request.remote_addr = "127.0.0.1"
    relay_app.request = report_request  # type: ignore[attr-defined]
    report_resp = relay_app.admin_verify_report(job_id)
    report_response = report_resp
    if hasattr(report_resp, "data") and hasattr(report_resp.data, "get_json"):
        report_response = report_resp.data
    report = report_response.get_json()
    assert report["verdict"] == "VERIFIED_OK"
