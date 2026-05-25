from __future__ import annotations

import json, subprocess, sys


def test_build_default():
    out = subprocess.check_output([sys.executable, "-m", "scripts.build_household_presence_camera_zone_resolver", "build-default"], text=True)
    assert "zones" in json.loads(out)
