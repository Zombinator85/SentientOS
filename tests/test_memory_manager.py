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
