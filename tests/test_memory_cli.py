from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Banner: This script requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
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
    reload(actuator)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    res = actuator.act({"type": "shell", "cmd": "echo hi"})
    monkeypatch.setattr(sys, 'argv', ['mc', 'actions', '--last', '1', '--reflect'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'echo hi' in out and res['reflection'] in out


def test_cli_reflections(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import memory_manager as mm
    from api import actuator
    reload(mm)
    reload(memory_cli)
    reload(actuator)
    actuator.WHITELIST = {'shell': ['echo'], 'http': [], 'timeout': 5}
    actuator.act({'type': 'shell', 'cmd': 'echo hi'}, explanation='demo')
    monkeypatch.setattr(sys, 'argv', ['mc', 'reflections', '--last', '1'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'demo' in out

def test_cli_goals(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import memory_manager as mm
    reload(mm)
    reload(memory_cli)
    mm.add_goal('demo', intent={'type': 'hello', 'name': 'Ada'})
    monkeypatch.setattr(sys, 'argv', ['mc', 'goals', '--status', 'open'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'demo' in out


def test_cli_add_goal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import memory_manager as mm
    reload(mm)
    reload(memory_cli)
    monkeypatch.setattr(sys, 'argv', ['mc', 'add_goal', 'demo', '--intent', '{"type":"hello","name":"Ada"}'])
    memory_cli.main()
    out = capsys.readouterr().out
    goals = mm.get_goals(open_only=False)
    assert goals and goals[0]['text'] == 'demo'


def test_cli_events_and_orchestrator(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import notification
    reload(notification)
    reload(memory_cli)
    notification.send('goal_created', {'id': 'g'})
    monkeypatch.setattr(sys, 'argv', ['mc', 'events', '--last', '1'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'goal_created' in out
    monkeypatch.setattr(sys, 'argv', ['mc', 'orchestrator', 'status'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'running' in out


def test_cli_reject_patch(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import self_patcher
    import notification
    reload(notification)
    reload(self_patcher)
    reload(memory_cli)
    p = self_patcher.apply_patch('note', auto=False)
    monkeypatch.setattr(sys, 'argv', ['mc', 'reject_patch', p['id']])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'Rejected' in out
    patches = self_patcher.list_patches()
    assert any(x['id'] == p['id'] and x.get('rejected') for x in patches)
    events = notification.list_events(2)
    assert any(e['event'] == 'patch_rejected' for e in events)


def test_cli_approve_patch(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import self_patcher
    import notification
    reload(notification)
    reload(self_patcher)
    reload(memory_cli)
    p = self_patcher.apply_patch('note', auto=False)
    monkeypatch.setattr(sys, 'argv', ['mc', 'approve_patch', p['id']])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'Approved' in out
    patches = self_patcher.list_patches()
    assert any(x['id'] == p['id'] and x.get('approved') for x in patches)
    events = notification.list_events(2)
    assert any(e['event'] == 'patch_approved' for e in events)


def test_cli_rollback_patch(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import self_patcher
    import notification
    reload(notification)
    reload(self_patcher)
    reload(memory_cli)
    p = self_patcher.apply_patch('note', auto=False)
    monkeypatch.setattr(sys, 'argv', ['mc', 'rollback_patch', p['id']])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'Rolled back' in out
    patches = self_patcher.list_patches()
    assert any(x['id'] == p['id'] and x.get('rolled_back') for x in patches)
    events = notification.list_events(2)
    assert any(e['event'] == 'patch_rolled_back' for e in events)

def test_cli_patch_event_listing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import self_patcher
    import notification
    reload(notification)
    reload(self_patcher)
    reload(memory_cli)
    actions = [
        ('approve_patch', 'patch_approved'),
        ('reject_patch', 'patch_rejected'),
        ('rollback_patch', 'patch_rolled_back'),
    ]
    for cmd, evt in actions:
        p = self_patcher.apply_patch(cmd, auto=False)
        monkeypatch.setattr(sys, 'argv', ['mc', cmd, p['id']])
        memory_cli.main()
        capsys.readouterr()
        monkeypatch.setattr(sys, 'argv', ['mc', 'events', '--last', '2'])
        memory_cli.main()
        out = capsys.readouterr().out
        assert evt in out


def test_cli_analytics(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import presence_analytics as pa
    import memory_manager as mm
    reload(mm)
    reload(pa)
    reload(memory_cli)
    mm.append_memory('demo', emotions={'Joy':0.9})
    monkeypatch.setattr(sys, 'argv', ['mc', 'analytics'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'emotion_trends' in out


def test_cli_tomb_listing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('MEMORY_DIR', str(tmp_path))
    from importlib import reload
    import memory_cli
    import memory_manager as mm
    reload(mm)
    reload(memory_cli)
    fid = mm.append_memory('gone', tags=['t'])
    mm.purge_memory(max_files=0, requestor='cli', reason='test')
    monkeypatch.setattr(sys, 'argv', ['mc', 'tomb', '--tag', 't'])
    memory_cli.main()
    out = capsys.readouterr().out
    assert 'gone' in out

