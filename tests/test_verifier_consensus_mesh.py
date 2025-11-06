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


def _make_remote_vote(job_id, report, hostname, signing_key, merkle_root):
    root = merkle_root if merkle_root is not None else merkle_root_for_report(report)
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


def test_mesh_solicit_and_vote_flow(relay_env, client):
    csrf = _get_csrf(client)
    job_id, _ = _start_simple_job(client, csrf)

    store = relay_env._VERIFIER_STORE
    registry = relay_env.registry
    report = store.get_report(job_id)
    bundle = store.get_bundle(job_id)
    assert bundle is not None

    remote_key = SigningKey.generate()
    remote_host = "mesh-remote"
    _register_remote(registry, remote_host, remote_key)

    response = client.post(
        "/admin/verify/consensus/submit",
        json={"job_id": job_id, "quorum_k": 2, "quorum_n": 2, "participants": [remote_host]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    solicit_payload = {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "quorum_k": 2,
        "quorum_n": 2,
        "requester": remote_host,
        "requester_sig": "",
        "bundle_inline": bundle,
    }
    message = _canonical_dump({
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "quorum_k": 2,
        "quorum_n": 2,
        "requester": remote_host,
    }).encode("utf-8")
    solicit_payload["requester_sig"] = base64.b64encode(remote_key.sign(message).signature).decode("ascii")

    solicit_response = client.post("/mesh/verify/solicit", json=solicit_payload)
    assert solicit_response.status_code == 200
    vote_payload = solicit_response.get_json()["vote"]
    assert vote_payload["voter_node"] != remote_host

    merkle_root = vote_payload.get("merkle_root") or vote_payload.get("proof_hash")
    remote_vote = _make_remote_vote(job_id, report, remote_host, remote_key, merkle_root)

    submit_response = client.post("/mesh/verify/submit_vote", json={"vote": remote_vote})
    assert submit_response.status_code == 200
    consensus = store.get_consensus(job_id)
    assert consensus is not None
    assert consensus["final_verdict"] == "VERIFIED_OK"
    trust = registry.get(remote_host)
    assert trust and trust.trust_score >= 2


def test_rate_limited_mesh_requests(relay_env, client, monkeypatch):
    relay_env._MESH_RATE_TRACKER.clear()
    monkeypatch.setattr(relay_env, "_MESH_RATE_LIMIT", 3)
    csrf = _get_csrf(client)
    job_id, _ = _start_simple_job(client, csrf)
    store = relay_env._VERIFIER_STORE
    registry = relay_env.registry
    report = store.get_report(job_id)
    bundle = store.get_bundle(job_id)
    remote_key = SigningKey.generate()
    remote_host = "rate-remote"
    _register_remote(registry, remote_host, remote_key)

    payload_base = {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "quorum_k": 1,
        "quorum_n": 1,
        "requester": remote_host,
        "bundle_inline": bundle,
    }

    def make_payload():
        core = {
            "job_id": job_id,
            "script_hash": report["script_hash"],
            "quorum_k": 1,
            "quorum_n": 1,
            "requester": remote_host,
        }
        signature = base64.b64encode(remote_key.sign(_canonical_dump(core).encode("utf-8")).signature).decode("ascii")
        payload = dict(payload_base)
        payload["requester_sig"] = signature
        return payload

    for _ in range(3):
        assert client.post("/mesh/verify/solicit", json=make_payload()).status_code == 200
    assert client.post("/mesh/verify/solicit", json=make_payload()).status_code == 429


def test_reject_untrusted_or_suspended_nodes(relay_env, client):
    csrf = _get_csrf(client)
    job_id, _ = _start_simple_job(client, csrf)
    store = relay_env._VERIFIER_STORE
    registry = relay_env.registry
    report = store.get_report(job_id)
    bundle = store.get_bundle(job_id)
    remote_key = SigningKey.generate()
    remote_host = "suspended-node"
    _register_remote(registry, remote_host, remote_key)

    client.post(
        "/admin/verify/consensus/submit",
        json={"job_id": job_id, "quorum_k": 1, "quorum_n": 1},
        headers={"X-CSRF-Token": csrf},
    )

    core = {
        "job_id": job_id,
        "script_hash": report["script_hash"],
        "quorum_k": 1,
        "quorum_n": 1,
        "requester": remote_host,
    }
    signature = base64.b64encode(remote_key.sign(_canonical_dump(core).encode("utf-8")).signature).decode("ascii")
    client.post(
        "/mesh/verify/solicit",
        json={**core, "bundle_inline": bundle, "requester_sig": signature},
    )

    registry.record_misbehavior(remote_host, "BAD_SIG")
    registry.record_misbehavior(remote_host, "BAD_SIG")

    merkle_root = merkle_root_for_report(report)
    remote_vote = _make_remote_vote(job_id, report, remote_host, remote_key, merkle_root)
    response = client.post("/mesh/verify/submit_vote", json={"vote": remote_vote})
    assert response.status_code == 403
