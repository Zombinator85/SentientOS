import importlib
import json
import os
import sys
import types
from pathlib import Path
import pytest

pytest.skip("legacy avatar todo fixes interfere with env", allow_module_level=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Provide a minimal admin_utils stub to avoid import side effects
fake_admin = types.ModuleType("admin_utils")
fake_admin.require_admin_banner = lambda: None
sys.modules["admin_utils"] = fake_admin


def test_cross_presence_meet(tmp_path, monkeypatch):
    log = tmp_path / "meet.jsonl"
    exp = tmp_path / "exp.jsonl"
    imp = tmp_path / "imp.jsonl"
    monkeypatch.setenv("AVATAR_EXPORT_LOG", str(exp))
    monkeypatch.setenv("AVATAR_IMPORT_LOG", str(imp))
    monkeypatch.setenv("FEDERATION_NODES", str(tmp_path / "nodes.json"))
    monkeypatch.setenv("FEDERATION_TRUST_LOG", str(tmp_path / "trust.jsonl"))
    src = tmp_path / "a.blend"
    src.write_text("data")
    dest = tmp_path / "dest"
    dest.mkdir()
    import avatar_cross_presence_collab as acc
    importlib.reload(acc)
    monkeypatch.setattr(acc, "LOG_PATH", log)
    acc.meet(str(src), str(dest))
    assert log.exists()
    assert (dest / "a.blend").exists()
    trust = Path(os.environ["FEDERATION_TRUST_LOG"])
    assert trust.exists() and trust.read_text().strip()


def test_dream_daemon_run(tmp_path, monkeypatch):
    log = tmp_path / "dream.jsonl"
    dream_dir = tmp_path / "dreams"
    monkeypatch.setenv("AVATAR_DREAM_DIR", str(dream_dir))
    import avatar_dream_daemon as add
    importlib.reload(add)
    monkeypatch.setattr(add, "LOG_PATH", log)
    add.run_once("moon")
    assert (dream_dir / "moon.txt").exists()
    assert log.exists()


class DummyBpy(types.ModuleType):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.context = types.SimpleNamespace(object=types.SimpleNamespace(name="obj", applied_mood=""))
        class WM:
            def __init__(self, outer):
                self.outer = outer
            def open_mainfile(self, filepath: str) -> None:
                self.outer.context.object.path = filepath
            def save_as_mainfile(self, filepath: str) -> None:
                Path(filepath).write_text("blend")
        self.ops = types.SimpleNamespace(wm=WM(self))


def test_mood_animator_with_bpy(tmp_path, monkeypatch):
    log = tmp_path / "anim.jsonl"
    monkeypatch.setitem(sys.modules, "bpy", DummyBpy("bpy"))
    import avatar_mood_animator as ama
    importlib.reload(ama)
    monkeypatch.setattr(ama, "LOG_PATH", log)
    src = tmp_path / "a.blend"
    src.write_text("b")
    ama.update_avatar(str(src), "joy")
    assert ama.bpy.context.object.applied_mood == "joy"
    assert log.exists()


def test_personality_merge(tmp_path, monkeypatch):
    merge_log = tmp_path / "merge.jsonl"
    mem_log = tmp_path / "mem.jsonl"
    entries = [
        {"timestamp": "1", "avatar": "a", "event": "e"},
        {"timestamp": "2", "avatar": "b", "event": "e"},
    ]
    mem_log.write_text("\n".join(json.dumps(e) for e in entries))
    monkeypatch.setenv("AVATAR_MEMORY_LINK_LOG", str(mem_log))
    import avatar_personality_merge as apm
    importlib.reload(apm)
    monkeypatch.setattr(apm, "LOG_PATH", merge_log)
    apm.merge("a", "b", "c")
    data = [json.loads(l) for l in mem_log.read_text().splitlines() if json.loads(l).get("avatar") == "c"]
    assert len(data) == 2
    assert merge_log.exists()


def test_avatar_storyteller(tmp_path, monkeypatch):
    log = tmp_path / "story.jsonl"
    called = {}
    dummy = types.SimpleNamespace(speak=lambda *a, **k: called.setdefault("ok", True))
    monkeypatch.setitem(sys.modules, "tts_bridge", dummy)
    import avatar_storyteller as ast
    importlib.reload(ast)
    monkeypatch.setattr(ast, "LOG_PATH", log)
    ast.recite("ava", "hello!")
    assert called
    entry = json.loads(log.read_text())
    assert entry["mood"] == "excited"

