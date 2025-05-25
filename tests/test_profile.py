import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import user_profile as up


def test_profile_update_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    profile = up.update_profile(name="Allen", partner="April")
    assert profile["name"] == "Allen"
    loaded = up.load_profile()
    assert loaded == profile

