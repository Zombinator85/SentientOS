import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sentientos
import sentientos.__main__ as smain
import runpy
import requests


def test_version_present():
    assert isinstance(sentientos.__version__, str)


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_main_runs(capsys, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResp({"uptime": 0}))
    sys.argv = ["sentientos", "status", "--url", "http://example.com/status"]
    runpy.run_module("sentientos.__main__", run_name="__main__")
    out = capsys.readouterr().out
    assert "uptime" in out

