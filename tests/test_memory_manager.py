"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))



def test_append_memory_creates_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    fragment_id = mm.append_memory("hello world", tags=["test"], source="unit")
    file_path = tmp_path / "raw" / f"{fragment_id}.json"
    assert file_path.exists()
    data = json.loads(file_path.read_text())
    assert data["text"] == "hello world"
    assert data["tags"] == ["test"]
    assert data["source"] == "unit"
    assert isinstance(data.get("emotions"), dict)


def test_append_memory_custom_emotions(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    custom = {e: 0.0 for e in mm.empty_emotion_vector().keys()}
    custom["Joy"] = 0.5
    fid = mm.append_memory("hi", emotions=custom)
    file_path = tmp_path / "raw" / f"{fid}.json"
    data = json.loads(file_path.read_text())
    assert data["emotions"]["Joy"] == 0.5


def test_get_context_returns_relevant_snippet(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    mm.append_memory("alpha beta gamma")
    mm.append_memory("beta delta")
    mm.append_memory("zeta eta")

    ctx = mm.get_context("beta", k=2)
    assert any("beta" in c for c in ctx)

import datetime

def test_purge_memory_removes_old(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    old_id = mm.append_memory("old fragment")
    new_id = mm.append_memory("new fragment")

    old_file = tmp_path / "raw" / f"{old_id}.json"
    data = json.loads(old_file.read_text())
    data["timestamp"] = (datetime.datetime.utcnow() - datetime.timedelta(days=2)).isoformat()
    old_file.write_text(json.dumps(data))

    mm.purge_memory(max_age_days=1)

    assert not old_file.exists()
    assert (tmp_path / "raw" / f"{new_id}.json").exists()


def test_summarize_memory_creates_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    mm.append_memory("summary test")
    mm.summarize_memory()
    day = datetime.datetime.utcnow().date().isoformat()
    summary = tmp_path / "distilled" / f"{day}.txt"
    assert summary.exists()
    assert "summary test" in summary.read_text()


def test_purge_memory_respects_max_files(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    id1 = mm.append_memory("frag one")
    id2 = mm.append_memory("frag two")
    id3 = mm.append_memory("frag three")

    path1 = tmp_path / "raw" / f"{id1}.json"
    data = json.loads(path1.read_text())
    data["timestamp"] = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
    path1.write_text(json.dumps(data))

    mm.purge_memory(max_files=2)

    assert not path1.exists()
    assert (tmp_path / "raw" / f"{id2}.json").exists()
    assert (tmp_path / "raw" / f"{id3}.json").exists()


def test_summarize_memory_includes_multiple_snippets(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    mm.append_memory("first snippet")
    mm.append_memory("second snippet")
    mm.summarize_memory()

    day = datetime.datetime.utcnow().date().isoformat()
    summary = tmp_path / "distilled" / f"{day}.txt"
    assert summary.exists()
    text = summary.read_text()
    assert "first snippet" in text
    assert "second snippet" in text


def test_embedding_retrieval(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("USE_EMBEDDINGS", "1")
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    mm.append_memory("dogs and cats")
    mm.append_memory("i like dogs")

    ctx = mm.get_context("dogs", k=1)
    assert ctx


def test_search_by_tags(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    mm.append_memory("one", tags=["a", "b"])
    mm.append_memory("two", tags=["b"])
    mm.append_memory("three", tags=["a", "b", "c"])

    res = mm.search_by_tags(["a", "b"], limit=2)
    assert len(res) == 2
    assert res[0]["text"] == "three"
    assert res[1]["text"] == "one"


def test_purge_archives_to_tomb(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm
    reload(mm)

    fid = mm.append_memory("obsolete", tags=["x"])
    mm.purge_memory(max_files=0, requestor="tester", reason="cleanup")

    tomb = tmp_path / "memory_tomb.jsonl"
    assert tomb.exists()
    lines = [json.loads(l) for l in tomb.read_text().splitlines() if l.strip()]
    assert lines and lines[0]["fragment"]["id"] == fid
    assert lines[0]["requestor"] == "tester"


def test_apply_forgetting_curve_removes_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("MEMORY_IMPORTANCE_FLOOR", "0.6")
    monkeypatch.setenv("MEMORY_HALF_LIFE_DAYS", "1")
    from importlib import reload
    import memory_manager as mm

    reload(mm)

    fid = mm.append_memory("fading", tags=["test"])
    path = tmp_path / "raw" / f"{fid}.json"
    data = json.loads(path.read_text())
    data["importance"] = 0.1
    data["last_accessed"] = (
        datetime.datetime.utcnow() - datetime.timedelta(days=30)
    ).isoformat()
    path.write_text(json.dumps(data))

    removed = mm.apply_forgetting_curve(requestor="pytest")
    assert removed == 1
    assert not path.exists()
    tomb = tmp_path / "memory_tomb.jsonl"
    assert tomb.exists()


def test_summarize_memory_creates_topic_capsule(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm

    reload(mm)
    mm.append_memory("topic summary", tags=["alpha"])
    mm.summarize_memory()
    topic = tmp_path / "topics" / "alpha.md"
    assert topic.exists()
    assert "topic summary" in topic.read_text()


def test_session_and_turn_capsules(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm

    reload(mm)
    mm.append_memory("first turn", tags=["session:alpha", "user_request"], source="unit")
    mm.append_memory("second turn", tags=["session:alpha"], source="unit")
    mm.summarize_memory()

    turn_file = tmp_path / "turns" / "alpha.json"
    session_file = tmp_path / "sessions" / "alpha.md"
    assert turn_file.exists()
    assert session_file.exists()
    assert "first turn" in session_file.read_text()


def test_curate_memory_runs_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import memory_manager as mm

    reload(mm)
    mm.append_memory("retain me", tags=["beta"])
    stats = mm.curate_memory()
    assert "removed" in stats
