import json
from pathlib import Path

from sentientos.federation.concord_daemon import ConcordDaemon, PeerSnapshot


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_concord_daemon_conflicts_and_realignment(tmp_path: Path) -> None:
    glossary = tmp_path / "glossary.json"
    glossary.write_text(json.dumps({"aligned": "alpha", "shared": "local"}), encoding="utf-8")
    doctrine = tmp_path / "doctrine.md"
    doctrine.write_text("Federation doctrine", encoding="utf-8")

    peer1_glossary = tmp_path / "peer1_glossary.json"
    peer1_glossary.write_text(json.dumps({"shared": "remote", "missing": "beta"}), encoding="utf-8")
    peer1_diff = tmp_path / "peer1_diff.jsonl"
    peer1_diff.write_text(json.dumps({"term": "shared", "suggested_definition": "remote", "priority": "high"}) + "\n",
                          encoding="utf-8")

    peer2_glossary = tmp_path / "peer2_glossary.json"
    peer2_glossary.write_text(json.dumps({"aligned": "alpha"}), encoding="utf-8")

    daemon = ConcordDaemon(glossary, doctrine, [peer1_diff])
    peers = [
        PeerSnapshot("peer1", peer1_glossary, peer1_diff),
        PeerSnapshot("peer2", peer2_glossary, None),
    ]
    reconciliation = daemon.reconcile(peers, tmp_path)

    report_entries = _read_jsonl(reconciliation["report_path"])
    assert any(entry["issue"] == "conflicted_definition" for entry in report_entries)
    assert any(entry["issue"] == "missing_alignment" for entry in report_entries)
    assert reconciliation["proposals"]
    assert reconciliation["realignment_event"] is None

    aligned_output = tmp_path / "aligned"
    aligned_output.mkdir()
    aligned_peers = [PeerSnapshot("peer2", peer2_glossary, None)]
    aligned_reconciliation = daemon.reconcile(aligned_peers, aligned_output)

    assert aligned_reconciliation["converged"] is True
    realignment_path = aligned_reconciliation["realignment_event"]
    assert realignment_path is not None and realignment_path.exists()
    realignment_entries = _read_jsonl(realignment_path)
    assert realignment_entries[0]["converged"] is True
