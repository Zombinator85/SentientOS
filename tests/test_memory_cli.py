import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_cli_imports():
    import memory_cli
    assert hasattr(memory_cli, "main")


def test_cli_inspect_and_forget(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import memory_cli
    import user_profile as up
    up.update_profile(color="blue")

    monkeypatch.setattr(sys, "argv", ["mc", "inspect"])
    memory_cli.main()
    captured = capsys.readouterr().out
    assert "color" in captured

    monkeypatch.setattr(sys, "argv", ["mc", "forget", "color"])
    memory_cli.main()
    assert "color" not in up.load_profile()

def test_cli_playback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import memory_manager as mm
    reload(mm)
    reload(memory_cli)
    mm.append_memory('hello', emotions={'Joy':0.9})
    monkeypatch.setattr(sys, 'argv', ['mc', 'playback', '--last', '1'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'hello' in out
    assert 'Joy' in out


def test_cli_actions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import memory_manager as mm
    from api import actuator
    reload(mm)
    reload(memory_cli)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    res = actuator.act({"type": "shell", "cmd": "echo hi"})
    monkeypatch.setattr(sys, 'argv', ['mc', 'actions', '--last', '1', '--reflect'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'echo hi' in out and res['reflection'] in out
