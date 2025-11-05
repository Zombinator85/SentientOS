import os
from importlib import reload
from pathlib import Path


def _configure(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("MEMORY_MODE", "personal")
    monkeypatch.setenv("MEM_DB_PATH", str(tmp_path / "secure.sqlite3"))
    monkeypatch.setenv("MEM_KEY_BACKEND", "passphrase")
    monkeypatch.setenv("MEM_PASSPHRASE", "export-pass")
    monkeypatch.setenv("MEM_KDF_ITERS", "600")

    import sys
    import types

    if "dotenv" not in sys.modules:
        stub = types.ModuleType("dotenv")
        stub.load_dotenv = lambda *_, **__: None  # type: ignore[attr-defined]
        sys.modules["dotenv"] = stub

    import memory_manager as mm
    reload(mm)
    import secure_memory_storage as storage
    reload(storage)
    import memory_governor as mg
    reload(mg)
    import mem_export
    reload(mem_export)
    return mg, storage, mem_export


def test_export_import_roundtrip(tmp_path, monkeypatch):
    mg, storage, mem_export = _configure(tmp_path, monkeypatch)

    mg.remember({"text": "alpha", "category": "event"})
    mg.remember({"text": "beta", "category": "dream"})

    archive = mem_export.export_encrypted(
        None,
        include_insights=True,
        include_dreams=True,
        passphrase="bridge",
    )
    assert archive

    db_path = Path(os.environ["MEM_DB_PATH"])
    if db_path.exists():
        db_path.unlink()

    reload(storage)
    reload(mem_export)

    stats = mem_export.import_encrypted(archive, passphrase="bridge")
    assert stats["imported"] == 2

    entries = list(storage.iterate_plaintext(limit=10))
    texts = {entry["text"] for entry in entries}
    assert {"alpha", "beta"}.issubset(texts)
