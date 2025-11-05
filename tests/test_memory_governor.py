from importlib import reload


def test_memory_governor_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("SENTIENTOS_ALLOW_DREAMING", raising=False)

    import memory_manager as mm

    reload(mm)

    import memory_governor as mg

    reload(mg)

    entry = mg.remember(
        {
            "category": "dream",
            "text": "Discovery moments filled me with joy.",
            "summary": "Discovery joy link",
            "tags": ["dream", "reflection", "goal_unfinished"],
            "emotions": {"Joy": 0.9},
            "importance": 0.85,
            "reflective": True,
        }
    )
    results = mg.recall("importance >= 0.8", k=5)
    assert any(mem.get("id") == entry.get("id") for mem in results)

    from importlib import reload as reload_module

    import dream_loop

    reload_module(dream_loop)

    narrative = dream_loop.generate_insight(results)
    assert isinstance(narrative, str)
    assert narrative

    summary = mg.reflect()
    assert hasattr(summary, "updated")
    assert hasattr(summary, "trimmed_snapshots")
