import json
import importlib
from pathlib import Path

import drift_audit
import sentient_autonomy as sa
import sentient_mesh as sm
from council_adapters.base_voice import VoiceExchange


class _StubMesh:
    def __init__(self) -> None:
        self.cycles = 0

    def cycle(self, jobs):
        self.cycles += 1
        assignments = {job.job_id: "node-1" for job in jobs}
        return type("_Snap", (), {"assignments": assignments})()


def test_drift_snapshot_reports_sizes(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text("entry\n" * 100)
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps([{"path": "a"}, {"path": "b"}]))
    log_paths = {
        "relay": tmp_path / "relay.log",
        "invariant": tmp_path / "invariant.log",
        "autonomy": tmp_path / "autonomy.log",
        "mesh": tmp_path / "mesh.log",
    }
    for path in log_paths.values():
        path.write_text("line\n" * 50)

    snapshot = drift_audit.snapshot(
        log_paths=log_paths, ledger_path=ledger_path, index_path=index_path
    )

    assert snapshot["capability_ledger"].bytes >= ledger_path.stat().st_size
    assert snapshot["capability_ledger"].classification == "audit-only"
    assert snapshot["unified_memory_index"].entries == 2
    assert set(log_paths.keys()).issubset(snapshot.keys())
    assert all(item.growth == "append-only" for key, item in snapshot.items() if key in log_paths)


def test_drift_metrics_do_not_change_autonomy_plan_order(monkeypatch):
    importlib.reload(sa)

    monkeypatch.setattr(
        sa.memory_governor,
        "mesh_metrics",
        lambda: {
            "open_goals": ["alpha", "beta", "gamma"],
            "trust_histogram": {},
            "active_council_sessions": 0,
            "emotion_consensus": {},
            "nodes": 0,
        },
    )
    engine = sa.SentientAutonomyEngine(mesh=_StubMesh())
    engine.start()

    snapshot = drift_audit.snapshot()
    first_cycle = engine.reflective_cycle(limit=2, force=True)
    second_snapshot = drift_audit.snapshot()

    assert [plan["goal"] for plan in first_cycle] == ["alpha", "beta"]
    assert snapshot["capability_ledger"].classification == "audit-only"
    assert second_snapshot["capability_ledger"].bytes == snapshot["capability_ledger"].bytes
    assert {plan["goal"] for plan in engine.status()["plans"]} == {"alpha", "beta"}


def test_mesh_exchange_rotation_preserves_order(tmp_path):
    mesh = sm.SentientMesh(transcripts_dir=tmp_path)
    for idx in range(130):
        exchange = VoiceExchange(
            voice="council",
            role="ask",
            content=f"c{idx}",
            signature=str(idx),
            advisory=False,
            timestamp=float(idx),
            metadata={},
        )
        mesh._append_exchange("job-1", exchange)

    records = mesh.sessions("job-1", limit=200)["job-1"]
    assert len(records) == 120
    assert records[0]["content"] == "c10"
    assert records[-1]["content"] == "c129"
