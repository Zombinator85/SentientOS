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


def _start_job(client, csrf_token):
    bundle = {"script": {"steps": []}, "claimed_run": None, "env": {}}
    response = client.post(
        "/admin/verify/submit",
        json={"bundle": bundle},
        headers={"X-CSRF-Token": csrf_token},
    )
    data = response.get_json()
    assert response.status_code == 200
    return data


def _make_vote(job_id, report, hostname, signing_key):
    payload = {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "proof_hash": report.get("proof_hash"),
        "merkle_root": report.get("proof_hash"),
    }
    signature = base64.b64encode(signing_key.sign(_canonical_dump(payload).encode("utf-8")).signature).decode("ascii")
    return {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "local_verdict": report.get("verdict", "VERIFIED_OK"),
        "proof_hash": report.get("proof_hash"),
        "merkle_root": report.get("proof_hash"),
        "metrics": {"proof_counts": report.get("proof_counts", {}), "diffs": len(report.get("diffs", []))},
        "voter_node": hostname,
        "voter_sig": signature,
        "ts": time.time(),
    }


def test_console_cancel_and_force_finalize_buttons(relay_env, client, monkeypatch):
    csrf = _get_csrf(client)

    # Cancel flow
    job_a = _start_job(client, csrf)
    response = client.post(
        "/admin/verify/consensus/submit",
        json={"job_id": job_a["job_id"], "quorum_k": 2, "quorum_n": 2},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    cancel = client.post(
        "/admin/verify/consensus/cancel",
        json={"job_id": job_a["job_id"], "reason": "test"},
        headers={"X-CSRF-Token": csrf},
    )
    cancel_payload = cancel.get_json()
    assert cancel.status_code == 200
    assert cancel_payload["snapshot"]["status"] == "CANCELED"

    # Force finalize flow
    job_b = _start_job(client, csrf)
    store = relay_env._VERIFIER_STORE
    registry = relay_env.registry
    report = store.get_report(job_b["job_id"])
    remote_key = SigningKey.generate()
    remote_host = "force-node"
    _register_remote(registry, remote_host, remote_key)

    submit = client.post(
        "/admin/verify/consensus/submit",
        json={"job_id": job_b["job_id"], "quorum_k": 2, "quorum_n": 2, "participants": [remote_host]},
        headers={"X-CSRF-Token": csrf},
    )
    assert submit.status_code == 200

    # Force finalize should fail while quorum unmet.
    pre_force = client.post(
        "/admin/verify/consensus/finalize",
        json={"job_id": job_b["job_id"], "reason": "fast"},
        headers={"X-CSRF-Token": csrf},
    )
    assert pre_force.status_code == 409

    vote_payload = _make_vote(job_b["job_id"], report, remote_host, remote_key)

    # Prevent automatic finalization so we can exercise the endpoint.
    with monkeypatch.context() as ctx:
        ctx.setattr(relay_env, "_maybe_finalise_consensus", lambda state, actor=None: None)
        submit_vote = client.post("/mesh/verify/submit_vote", json={"vote": vote_payload})
        assert submit_vote.status_code == 200

    force = client.post(
        "/admin/verify/consensus/finalize",
        json={"job_id": job_b["job_id"], "reason": "operator"},
        headers={"X-CSRF-Token": csrf},
    )
    payload = force.get_json()
    assert force.status_code == 200
    assert payload["snapshot"]["status"] == "FINALIZED"
    assert payload["snapshot"].get("force_reason") == "operator"
