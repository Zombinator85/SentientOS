from importlib import reload


def test_incognito_prevents_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("MEM_INCOGNITO", "1")
    monkeypatch.setenv("MEMORY_MODE", "legacy")

    import sys
    import types

    if "dotenv" not in sys.modules:
        stub = types.ModuleType("dotenv")
        stub.load_dotenv = lambda *_, **__: None  # type: ignore[attr-defined]
        sys.modules["dotenv"] = stub

    import memory_manager as mm
    reload(mm)
    import memory_governor as mg
    reload(mg)

    result = mg.remember({"text": "hidden thoughts", "category": "event"})
    assert result == ""

    fragments = list(mm.iter_fragments(limit=10, reverse=False))
    assert fragments == []
