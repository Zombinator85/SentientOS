import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sentient_banner import print_timestamped_closing


def test_timestamped_closing(capsys):
    print_timestamped_closing()
    out = capsys.readouterr().out
    assert "Presence is law" in out and "[" in out and "]" in out
