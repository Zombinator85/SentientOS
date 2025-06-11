"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval

import json
from pathlib import Path
from flask_stub import Flask
import privilege_lint as pl
"""Simple Flask view for privileged command audit log."""


app = Flask(__name__)
LOG = pl.AUDIT_FILE

TABLE = """<html><body><h3>Privileged Command Audit</h3>
<table border='1'><tr><th>Time</th><th>Tool</th><th>Command</th></tr>{rows}</table>
</body></html>"""


@app.route("/")
def audit_table() -> str:
    if not LOG.exists():
        return TABLE.format(rows="")
    lines = LOG.read_text(encoding="utf-8").splitlines()[-100:]
    rows = []
    for ln in lines:
        try:
            d = json.loads(ln)
        except Exception:
            continue
        ts = d.get("timestamp", "")
        tool = str(d.get("tool", ""))
        cmd = str(d.get("command", ""))
        rows.append(f"<tr><td>{ts}</td><td>{tool}</td><td>{cmd}</td></tr>")
    return TABLE.format(rows="\n".join(rows))


def run() -> None:
    app.run(port=5010)


if __name__ == "__main__":  # pragma: no cover - manual
    run()
