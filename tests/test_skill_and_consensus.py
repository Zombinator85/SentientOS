from importlib import reload


def test_skill_registry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))

    import memory_manager as mm

    reload(mm)

    import skill_library as sl

    reload(sl)

    goal = {"id": "goal-1", "intent": {"type": "shell"}, "text": "run diagnostics"}
    result = {"status": "finished", "reflection": "Diagnostics successful", "log_id": "abc123"}

    skill = sl.register_skill(goal, result)
    assert skill is not None

    skills = sl.suggest_skills("diagnostics")
    assert skills and skills[0]["id"] == skill["id"]

    log = (tmp_path / "skills.jsonl").read_text()
    assert "goal-1" in log


def test_council_consensus_blocks_dangerous_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))

    import memory_manager as mm

    reload(mm)

    import council_consensus as cc

    reload(cc)

    verdict = cc.deliberate({"type": "shell", "cmd": "rm -rf /"}, "danger")
    assert verdict["approved"] is False
    raw_files = list((tmp_path / "raw").glob("*.json"))
    assert raw_files  # memory log created


def test_council_consensus_allows_safe_http(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))

    import memory_manager as mm

    reload(mm)

    import council_consensus as cc

    reload(cc)

    verdict = cc.deliberate({"type": "http", "url": "https://example.com"}, "fetch data")
    assert verdict["approved"] is True
