import os
import time
from flask import Flask, jsonify
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

START_TS = time.time()

app = Flask(__name__)


def _pending_patches() -> int:
    # Placeholder: count of pending patches could come from a queue file
    return int(os.getenv("SENTIENT_PENDING_PATCHES", "0"))


def _cost_today() -> float:
    return float(os.getenv("SENTIENT_COST_TODAY", "0"))


@app.get("/status")
def status() -> "flask.Response":
    uptime = int(time.time() - START_TS)
    return jsonify(
        {
            "uptime": uptime,
            "pending_patches": _pending_patches(),
            "cost_today": _cost_today(),
        }
    )


if __name__ == "__main__":  # pragma: no cover - CLI
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

