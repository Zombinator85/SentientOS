from importlib import reload


def _prepare(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("MEMORY_MODE", "personal")
    monkeypatch.setenv("MEM_DB_PATH", str(tmp_path / "secure.sqlite3"))
    monkeypatch.setenv("MEM_KEY_BACKEND", "passphrase")
    monkeypatch.setenv("MEM_PASSPHRASE", "rotate-pass")
    monkeypatch.setenv("MEM_KDF_ITERS", "800")

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
    import mem_admin
    reload(mem_admin)
    return mg, storage, mem_admin


def test_rotate_reencrypts_existing_rows(tmp_path, monkeypatch):
    mg, storage, mem_admin = _prepare(tmp_path, monkeypatch)

    texts = ["first memory", "second memory", "third memory"]
    for text in texts:
        mg.remember({"text": text, "category": "event"})

    backend = storage.get_backend()
    old_key = backend.get_active_key_id()

    result = mem_admin.rotate_keys(reencrypt_batch=10)
    assert result["rotated"] is True
    new_key = result["new_key"]
    assert new_key != old_key

    rows = storage.dump_raw_rows()
    assert rows
    assert all(row["key_id"] == new_key for row in rows)
