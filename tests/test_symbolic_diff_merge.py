from pathlib import Path
import json

from sentientos.daemons.symbolic_diff_daemon import SymbolicDiffDaemon
from tools.symbolic_merge import resolve_conflicts


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, entries) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


def test_symbolic_diff_and_merge(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    peer_root = tmp_path / "peer"

    # Local snapshot
    _write_json(local_root / "config" / "canonical_glossary.json", {"guardian_role": {"definition": "guardian"}})
    _write_json(local_root / "glow" / "contexts" / "identity_manifest.json", {"roles": [{"symbol_id": "guardian_role", "name": "guardian"}]})
    _write_jsonl(
        local_root / "integration" / "ledger.jsonl",
        [{"symbol_id": "memory_fragment", "tags": ["local", "guardian"], "narrative": "local ledger note"}],
    )
    _write_json(
        local_root / "glow" / "fragments" / "story.json",
        {"symbol_id": "memory_fragment", "tags": ["local"], "narrative": "Local story"},
    )

    # Peer snapshot
    _write_json(peer_root / "config" / "canonical_glossary.json", {"guardian_role": {"definition": "sentinel"}})
    _write_json(peer_root / "glow" / "contexts" / "identity_manifest.json", {"roles": [{"symbol_id": "guardian_role", "name": "sentinel"}]})
    _write_jsonl(
        peer_root / "integration" / "ledger.jsonl",
        [{"symbol_id": "memory_fragment", "tags": ["remote", "sentinel"], "narrative": "remote ledger note"}],
    )
    _write_json(
        peer_root / "glow" / "fragments" / "story.json",
        {"symbol_id": "memory_fragment", "tags": ["remote"], "narrative": "Remote story"},
    )

    daemon = SymbolicDiffDaemon(base_path=local_root)
    conflict_path = tmp_path / "symbolic_conflict.jsonl"
    conflicts = daemon.run(peer_root, output_path=conflict_path)

    assert len(conflicts) == 4
    with conflict_path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline().strip()
    assert "guardian_role" in first_line

    merge_log_path = tmp_path / "symbolic_merge_log.jsonl"
    council_queue_path = tmp_path / "council_queue.jsonl"

    # Council path queues proposals
    council_records = resolve_conflicts(conflict_path, "council", merge_log_path, council_queue_path)
    assert len(council_records) == 4
    assert council_queue_path.exists()
    with council_queue_path.open("r", encoding="utf-8") as handle:
        queue_lines = handle.readlines()
    assert any("guardian_role" in line for line in queue_lines)

    # Peer acceptance path writes applied value
    merge_records = resolve_conflicts(conflict_path, "peer", merge_log_path)
    assert merge_log_path.exists()
    assert len(merge_records) == 4
    assert any(record.get("applied_value") == "sentinel" for record in merge_records)
