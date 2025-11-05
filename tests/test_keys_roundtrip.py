import os
import sqlite3
from importlib import reload


def _setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("MEMORY_MODE", "personal")
    monkeypatch.setenv("MEM_DB_PATH", str(tmp_path / "store.sqlite3"))
    monkeypatch.setenv("MEM_KEY_BACKEND", "passphrase")
    monkeypatch.setenv("MEM_PASSPHRASE", "secret-pass")
    monkeypatch.setenv("MEM_KDF_ITERS", "1000")
    monkeypatch.setenv("MEM_INCOGNITO", "0")

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
    return mg, storage


def test_secure_memory_roundtrip(tmp_path, monkeypatch):
    mg, storage = _setup_env(tmp_path, monkeypatch)

    entry = mg.remember({"text": "Whispered secrets", "category": "insight"})
    assert entry["text"] == "Whispered secrets"

    # ensure ciphertext stored in sqlite database
    conn = sqlite3.connect(os.environ["MEM_DB_PATH"])
    cur = conn.execute("SELECT ciphertext FROM mem_fragments")
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None
    ciphertext = row[0]
    assert b"Whispered" not in ciphertext

    decrypted = list(storage.iterate_plaintext(limit=5))
    assert decrypted
    assert any(item["text"] == "Whispered secrets" for item in decrypted)
