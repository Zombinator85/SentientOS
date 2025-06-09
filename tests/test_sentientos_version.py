import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sentientos
import sentientos.__main__ as smain
import runpy


def test_version_present():
    assert isinstance(sentientos.__version__, str)


def test_main_runs(capsys):
    runpy.run_module("sentientos.__main__", run_name="__main__")
    out = capsys.readouterr().out
    assert "SentientOS" in out

