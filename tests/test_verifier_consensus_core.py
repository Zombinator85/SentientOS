import base64
import json
import time
from dataclasses import replace

import pytest
from nacl.signing import SigningKey

from sentient_verifier import (
    ProofTrace,
    SentientVerifier,
    VerificationReport,
    Vote,
    merkle_root_for_report,
    merge_votes,
    verify_vote_signatures,
)


def _canonical_dump(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_merkle_root_stability_and_vote_signatures():
    verifier = SentientVerifier()
    report = VerificationReport(
        job_id="job-1",
        script_hash="sha256:deadbeef",
        from_node=None,
        verifier_node=verifier._local_hostname(),
        verdict="VERIFIED_OK",
        score=1.0,
    )
    trace = ProofTrace(step=0, status="PASS", post="state0")
    report.proofs = [trace]
    report.proof_counts = {"pass": 1, "fail": 0, "error": 0}
    report.proof_hash = verifier._proof_hash(report.proofs)

    root_direct = merkle_root_for_report(report)
    assert root_direct is not None
    root_serialised = merkle_root_for_report(report.to_dict())
    assert root_direct == root_serialised

    vote = verifier.make_vote(report)
    assert verify_vote_signatures((vote,), verifier._registry)


def test_merge_votes_quorum_paths_majority_and_inconclusive():
    verifier = SentientVerifier()
    report = VerificationReport(
        job_id="job-majority",
        script_hash="sha256:feedface",
        from_node=None,
        verifier_node=verifier._local_hostname(),
        verdict="VERIFIED_OK",
        score=1.0,
    )
    trace = ProofTrace(step=0, status="PASS", post="ok")
    report.proofs = [trace]
    report.proof_counts = {"pass": 1, "fail": 0, "error": 0}
    report.proof_hash = verifier._proof_hash(report.proofs)
    vote_a = verifier.make_vote(report)

    remote_key = SigningKey.generate()
    payload = {
        "job_id": report.job_id,
        "script_hash": report.script_hash,
        "proof_hash": report.proof_hash,
        "merkle_root": merkle_root_for_report(report),
    }
    signature = base64.b64encode(remote_key.sign(_canonical_dump(payload).encode("utf-8")).signature).decode("ascii")
    remote_host = "remote-majority"
    verifier._registry.register_or_update(
        remote_host,
        "127.0.0.1",
        trust_level="trusted",
        trust_score=1,
        capabilities={
            "verifier_capable": True,
            "verifier_pubkey": base64.b64encode(remote_key.verify_key.encode()).decode("ascii"),
        },
    )
    vote_b = Vote(
        job_id=report.job_id,
        script_hash=report.script_hash,
        local_verdict="VERIFIED_OK",
        proof_hash=report.proof_hash,
        merkle_root=merkle_root_for_report(report),
        metrics={"proof_counts": report.proof_counts, "diffs": 0},
        voter_node=remote_host,
        voter_sig=signature,
        ts=time.time(),
    )

    consensus = merge_votes((vote_a, vote_b), quorum_k=2, quorum_n=2)
    assert consensus.final_verdict == "VERIFIED_OK"
    assert consensus.merkle_root == vote_a.merkle_root
    assert len(consensus.votes) == 2

    disputed = replace(vote_b, local_verdict="DIVERGED")
    inconclusive = merge_votes((vote_a, disputed), quorum_k=2, quorum_n=2)
    assert inconclusive.final_verdict == "INCONCLUSIVE"


def test_double_vote_conflict_detects_nondeterminism():
    vote = Vote(
        job_id="conflict",
        script_hash="sha256:00",
        local_verdict="VERIFIED_OK",
        proof_hash="hash-a",
        merkle_root="root-a",
        metrics={},
        voter_node="node-a",
        voter_sig="sig-a",
        ts=1.0,
    )
    conflict = replace(vote, proof_hash="hash-b", merkle_root="root-b", voter_sig="sig-b", ts=2.0)
    with pytest.raises(ValueError):
        merge_votes((vote, conflict), quorum_k=1, quorum_n=2)
