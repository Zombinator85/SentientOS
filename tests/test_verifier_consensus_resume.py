import base64
import json
import time
from importlib import reload

import pytest
from nacl.signing import SigningKey


def _prepare_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "1")
    monkeypatch.setenv("SAFETY_LOG_ENABLED", "0")


@pytest.fixture
def relay_env(monkeypatch, tmp_path):
    _prepare_env(monkeypatch, tmp_path)
    import relay_app

    module = reload(relay_app)
    module.app.config["TESTING"] = True
    yield module


@pytest.fixture
def client(relay_env):
    return relay_env.app.test_client()


def _get_csrf(client):
    response = client.get("/admin/status")
    payload = response.get_json()
    assert response.status_code == 200
    return payload["csrf_token"]


def _canonical_dump(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _register_remote(registry, hostname, signing_key):
    registry.register_or_update(
        hostname,
        "127.0.0.1",
        trust_level="trusted",
        trust_score=1,
        capabilities={
            "verifier_capable": True,
            "verifier_pubkey": base64.b64encode(signing_key.verify_key.encode()).decode("ascii"),
        },
    )


def _start_simple_job(client, csrf_token):
    bundle = {"script": {"steps": []}, "claimed_run": None, "env": {}}
    response = client.post(
        "/admin/verify/submit",
        json={"bundle": bundle},
        headers={"X-CSRF-Token": csrf_token},
    )
    data = response.get_json()
    assert response.status_code == 200
    return data["job_id"], data["script_hash"]


def _make_remote_vote(job_id, report, hostname, signing_key, merkle_root=None):
    root = merkle_root if merkle_root is not None else report.get("proof_hash")
    payload = {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "proof_hash": report.get("proof_hash"),
        "merkle_root": root,
    }
    signature = base64.b64encode(signing_key.sign(_canonical_dump(payload).encode("utf-8")).signature).decode("ascii")
    metrics = {
        "proof_counts": report.get("proof_counts", {}),
        "diffs": len(report.get("diffs", [])),
    }
    return {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "local_verdict": report.get("verdict", "INCONCLUSIVE"),
        "proof_hash": report.get("proof_hash"),
        "merkle_root": root,
        "metrics": metrics,
        "voter_node": hostname,
        "voter_sig": signature,
        "ts": time.time(),
    }


def test_resume_inflight_merges_after_restart(monkeypatch, relay_env, client):
    csrf = _get_csrf(client)
    job_id, _ = _start_simple_job(client, csrf)
    store = relay_env._VERIFIER_STORE
    registry = relay_env.registry
    report = store.get_report(job_id)
    remote_key = SigningKey.generate()
    remote_host = "mesh-restart"
    _register_remote(registry, remote_host, remote_key)

    response = client.post(
        "/admin/verify/consensus/submit",
        json={"job_id": job_id, "quorum_k": 2, "quorum_n": 2, "participants": [remote_host]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    state_path = store._state_dir / f"{job_id}.json"
    assert state_path.exists()

    # Simulate relay restart.
    module = reload(relay_env)
    module.app.config["TESTING"] = True
    new_client = module.app.test_client()

    # Registry needs the remote node again after reload.
    _register_remote(module.registry, remote_host, remote_key)

    status = new_client.get(f"/admin/verify/consensus/status?job_id={job_id}").get_json()
    assert status["resumed"] is True
    assert status["status"] == "RUNNING"

    vote_payload = _make_remote_vote(job_id, report, remote_host, remote_key, response.get_json()["vote"]["merkle_root"])
    submit = new_client.post("/mesh/verify/submit_vote", json={"vote": vote_payload})
    assert submit.status_code == 200

    consensus = module._VERIFIER_STORE.get_consensus(job_id)
    assert consensus is not None
    assert consensus["final_verdict"] == "VERIFIED_OK"

    status_after = new_client.get(f"/admin/verify/consensus/status?job_id={job_id}").get_json()
    assert status_after["status"] == "FINALIZED"
    assert status_after.get("resumed") is True
