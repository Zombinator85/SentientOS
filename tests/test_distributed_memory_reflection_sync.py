import importlib
from datetime import datetime, timezone


def _reload_module(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("NODE_TOKEN", "sync-secret")
    module = importlib.reload(importlib.import_module("distributed_memory"))
    module.NODE_TOKEN = "sync-secret"
    return module


def test_reflection_receive_roundtrip(monkeypatch, tmp_path):
    module = _reload_module(monkeypatch, tmp_path)
    sync = module.DistributedMemorySynchronizer(interval_seconds=0.1)

    monkeypatch.setattr(module.registry, "iter_remote_nodes", lambda *a, **k: [], raising=False)

    published = []
    monkeypatch.setattr(module.pulse_bus, "publish", lambda event: published.append(event))

    summary = {
        "summary_id": "cycle-9",
        "cycle": 9,
        "summary": "Completed reflection loop",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "next_priorities": [{"id": "p1", "text": "Follow up"}],
        "successes": 2,
        "failures": 0,
        "origin": "local",
    }

    packet = sync._encode_reflection_summary(summary)
    assert packet is not None

    result = sync.receive_reflection(packet, source="ally-node")
    assert result["accepted"] is True
    assert result["summary_id"] == "cycle-9"

    duplicate = sync.receive_reflection(packet, source="ally-node")
    assert duplicate["duplicate"] is True

    log_path = sync._reflection_log
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "cycle-9" in content

    assert published
    assert published[-1]["event_type"] == "federated_reflection_received"
