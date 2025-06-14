"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Serve reflection tag cloud image via Flask."""
from pathlib import Path
from flask_stub import Flask, send_file
from reflection_tag_cloud import generate_cloud

app = Flask(__name__)
IMG = Path("tag_cloud.png")


@app.route("/tag_cloud")
def tag_cloud() -> object:
    if not IMG.exists():
        generate_cloud(IMG)
    if IMG.exists():
        return send_file(IMG)
    return "no data", 404


if __name__ == "__main__":  # pragma: no cover - manual
    app.run(port=5011)
