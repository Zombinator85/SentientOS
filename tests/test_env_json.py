"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import json
import subprocess
import sys


def test_env_json_output() -> None:
    cp = subprocess.run(
        [sys.executable, "-m", "privilege_lint.env", "report", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(cp.stdout)
    for key in ["node", "go", "dmypy", "pyesprima"]:
        assert key in data
        assert isinstance(data[key]["available"], bool)
        assert isinstance(data[key]["info"], str)
