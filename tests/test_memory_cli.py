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
