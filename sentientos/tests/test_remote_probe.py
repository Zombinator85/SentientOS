from __future__ import annotations

import json
from pathlib import Path

from scripts.remote_probe import run_probe
from sentientos.attestation import append_jsonl
from sentientos.forge_index import rebuild_index


def _seed_local(tmp_path: Path, *, policy_hash: str = "policy-aaa") -> None:
    (tmp_path / "glow/forge/attestation/snapshots").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/integrity").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/attestation/signatures/attestation_snapshots").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    snapshot = {
        "schema_version": 1,
        "ts": "2099-01-01T00:00:00Z",
        "policy_hash": policy_hash,
        "integrity_status_hash": "int-aaa",
        "latest_rollup_sig_hash": "roll-a",
        "latest_strategic_sig_hash": "strat-a",
        "latest_goal_graph_hash": "goal-a",
        "witness_summary": {},
    }
    integrity = {"schema_version": 1, "ts": "2099-01-01T00:00:00Z", "status": "ok", "policy_hash": policy_hash, "integrity_status_hash": "int-aaa"}
    (tmp_path / "glow/forge/attestation/snapshots/snapshot_local.json").write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
    (tmp_path / "glow/forge/integrity/status_local.json").write_text(json.dumps(integrity) + "\n", encoding="utf-8")
    append_jsonl(tmp_path / "glow/forge/attestation/signatures/attestation_snapshots/signatures_index.jsonl", {"sig_hash": "4a2f00034a1d9ff4acde013b9e39b1680a73afb35f71d5232e47a21ad3c1e57e"})


def test_remote_probe_ok_hmac_bundle(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_local(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_SIGNING", "hmac-test")

    report, exit_code = run_probe(
        root=tmp_path,
        bundle_path=Path("sentientos/tests/fixtures/remote_bundle_minimal/remote_bundle"),
        last_n=25,
        write=True,
    )

    assert exit_code == 0
    remote_verification = report["remote_verification"]
    assert remote_verification["bundle_hashes_ok"]["status"] == "ok"
    assert remote_verification["attestation_snapshot_chain"]["status"] == "ok"


def test_remote_probe_tamper_detected(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_local(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")

    _report, exit_code = run_probe(
        root=tmp_path,
        bundle_path=Path("sentientos/tests/fixtures/remote_bundle_tampered/remote_bundle"),
        last_n=25,
        write=False,
    )

    assert exit_code == 2


def test_remote_probe_operator_stream_missing_skips(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_local(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")

    report, exit_code = run_probe(
        root=tmp_path,
        bundle_path=Path("sentientos/tests/fixtures/remote_bundle_missing_operator/remote_bundle"),
        last_n=25,
        write=False,
    )

    assert exit_code == 1
    assert report["remote_verification"]["operator_reports_chain"]["status"] == "skipped_missing"


def test_remote_probe_divergence_precedence(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_local(tmp_path, policy_hash="policy-local")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_SIGNING", "hmac-test")

    report, exit_code = run_probe(
        root=tmp_path,
        bundle_path=Path("sentientos/tests/fixtures/remote_bundle_minimal/remote_bundle"),
        last_n=25,
        write=False,
    )

    assert exit_code == 2
    assert report["compare_remote_to_local"]["divergence_reasons"][0] == "policy_hash_mismatch"


def test_index_overlay_remote_probe_fields(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_local(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_SIGNING", "hmac-test")
    run_probe(
        root=tmp_path,
        bundle_path=Path("sentientos/tests/fixtures/remote_bundle_minimal/remote_bundle"),
        last_n=25,
        write=True,
    )

    payload = rebuild_index(tmp_path)
    assert payload["last_remote_probe_remote_node_id"] == "remote-node-1"
    assert payload["last_remote_probe_status"] == "ok"
