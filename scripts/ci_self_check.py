from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import subprocess
from typing import Any

AUTO = {"env": {"LUMOS_AUTO_APPROVE": "1"}}


def run(cmd: str, **kw: Any) -> subprocess.CompletedProcess[str]:
    print(f"🔧 {cmd}")
    return subprocess.run(cmd, shell=True, check=True, **kw)

run("python scripts/ritual_enforcer.py --fix")
run("python -m scripts.verify_audits logs/ --auto-repair", **AUTO)
run("python -m pip install -e .[dev]", **AUTO)
run("mypy --strict --exclude tests sentientos", **AUTO)
run("python -m scripts.run_tests -q -m 'not env'", **AUTO)
print("✅ All CI gates passed.")
