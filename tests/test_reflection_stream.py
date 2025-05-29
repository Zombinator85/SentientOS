import os
import sys
import importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import memory_manager as mm
import reflection_stream as rs
import plugin_framework as pf
import health_monitor as hm


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "mem"))
    monkeypatch.setenv("TRUST_DIR", str(tmp_path / "trust"))
    monkeypatch.setenv("REFLECTION_DIR", str(tmp_path / "reflect"))
    monkeypatch.setenv("GP_PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    importlib.reload(mm)
    importlib.reload(rs)
    importlib.reload(pf)
    importlib.reload(hm)
    pf.load_plugins()


def test_plugin_failure_logged(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    failing = plugins / "bad.py"
    failing.write_text("""from plugin_framework import BasePlugin\nclass B(BasePlugin):\n    def execute(self,e): raise RuntimeError('x')\n    def simulate(self,e): raise RuntimeError('x')\n\ndef register(r): r('bad', B())\n""", encoding='utf-8')
    setup_env(tmp_path, monkeypatch)
    pf.run_plugin('bad')
    logs = rs.recent(2)
    events = [l['event'] for l in logs]
    assert {'failure', 'escalation'} & set(events)


def test_health_escalation(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    def check():
        return False, 'broken'

    def heal():
        return False

    hm.register('dummy', check, heal)
    hm.check_all()
    logs = rs.recent(1)
    assert logs and logs[0]['event'] in {'escalation', 'failure'}

