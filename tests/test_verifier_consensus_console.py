import base64
import json
import time
from importlib import reload

import pytest
from nacl.signing import SigningKey

from sentient_verifier import merkle_root_for_report


def _prepare_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONSOLE_ENABLED", "1")


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


def _canonical_dump(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _start_job(client, csrf_token):
    payload = {"bundle": {"script": {"steps": []}, "claimed_run": None, "env": {}}}
    response = client.post("/admin/verify/submit", json=payload, headers={"X-CSRF-Token": csrf_token})
    assert response.status_code == 200
    return response.get_json()["job_id"]


def _make_vote(job_id, report, hostname, signing_key):
    payload = {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "proof_hash": report.get("proof_hash"),
        "merkle_root": merkle_root_for_report(report),
    }
    signature = base64.b64encode(signing_key.sign(_canonical_dump(payload).encode("utf-8")).signature).decode("ascii")
    return {
        **payload,
        "local_verdict": report.get("verdict", "INCONCLUSIVE"),
        "metrics": {"proof_counts": report.get("proof_counts", {}), "diffs": len(report.get("diffs", []))},
        "voter_node": hostname,
        "voter_sig": signature,
    }


def test_console_live_quorum_progress(relay_env, client):
    csrf = _get_csrf(client)
    job_id = _start_job(client, csrf)
    store = relay_env._VERIFIER_STORE
    registry = relay_env.registry
    remote_key = SigningKey.generate()
    remote_host = "console-remote"
    _register_remote(registry, remote_host, remote_key)

    response = client.post(
        "/admin/verify/consensus/submit",
        json={"job_id": job_id, "quorum_k": 2, "quorum_n": 2, "participants": [remote_host]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    status = client.get(f"/admin/verify/consensus/status?job_id={job_id}")
    data = status.get_json()
    assert status.status_code == 200
    assert data["received"] == 1
    assert data["needed"] == 1
    assert data["provisional_verdict"] == "INCONCLUSIVE"
    assert remote_host in data["participants"]
    assert data["finalized"] is False


def test_start_consensus_modal_and_finalize_render(relay_env, client):
    csrf = _get_csrf(client)
    job_id = _start_job(client, csrf)
    store = relay_env._VERIFIER_STORE
    registry = relay_env.registry
    remote_key = SigningKey.generate()
    remote_host = "console-final"
    _register_remote(registry, remote_host, remote_key)

    submit = client.post(
        "/admin/verify/consensus/submit",
        json={"job_id": job_id, "quorum_k": 2, "quorum_n": 2, "participants": [remote_host]},
        headers={"X-CSRF-Token": csrf},
    )
    payload = submit.get_json()
    assert submit.status_code == 200
    assert "snapshot" in payload

    report = store.get_report(job_id)
    vote = _make_vote(job_id, report, remote_host, remote_key)
    vote["ts"] = time.time()
    response = client.post("/mesh/verify/submit_vote", json={"vote": vote})
    assert response.status_code == 200

    report_response = client.get(f"/admin/verify/consensus/report?job_id={job_id}")
    consensus = report_response.get_json()
    assert report_response.status_code == 200
    assert consensus["final_verdict"] == "VERIFIED_OK"
    assert consensus["report_url"].endswith(job_id)
