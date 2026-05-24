from __future__ import annotations

import json
import subprocess
import sys


def test_script_build_validate_summarize(tmp_path) -> None:
    out = tmp_path / "inventory.json"
    cmd = [sys.executable, "scripts/build_household_presence_sensor_inventory.py", "build-default", "--output", str(out)]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] in {"inventory_ready", "inventory_ready_with_warnings"}

    proc2 = subprocess.run([sys.executable, "scripts/build_household_presence_sensor_inventory.py", "validate"], check=False, capture_output=True, text=True)
    assert proc2.returncode == 0

    proc3 = subprocess.run([sys.executable, "scripts/build_household_presence_sensor_inventory.py", "summarize"], check=False, capture_output=True, text=True)
    assert proc3.returncode == 0
    assert "status=" in proc3.stdout
