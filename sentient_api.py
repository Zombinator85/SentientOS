import os
import time
from typing import Any

from flask import Flask, jsonify, Response, g
from prometheus_client import Gauge, generate_latest
from admin_utils import require_admin_banner, require_lumos_approval
import tenant_middleware as tm

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

START_TS = time.time()

app = Flask(__name__)

REQUEST_GAUGE = Gauge(
    "sentientos_tenant_requests_total",
    "Number of requests per tenant",
    ["tenant"],
)
COST_GAUGE = Gauge(
    "sentientos_tenant_cost_usd",
    "Accumulated cost per tenant",
    ["tenant"],
)


@app.before_request
def _apply_tenant() -> None:
    tenant = tm.get_tenant_id()
    g.tenant_id = tenant
    tm.rate_limit()
    tm.check_cost_limit()
    REQUEST_GAUGE.labels(tenant=tenant).inc()
    COST_GAUGE.labels(tenant=tenant).set(tm.tenant_cost_metric().get(tenant, 0.0))


def _pending_patches() -> int:
    # Placeholder: count of pending patches could come from a queue file
    return int(os.getenv("SENTIENT_PENDING_PATCHES", "0"))


def _cost_today() -> float:
    return float(os.getenv("SENTIENT_COST_TODAY", "0"))


@app.get("/status")
def status() -> Response:
    uptime = int(time.time() - START_TS)
    tenant = getattr(g, "tenant_id", "public")
    tenant_cost = tm.tenant_cost_metric().get(tenant, 0.0)
    remaining = max(0, tm.TENANT_RATE_LIMIT - len(tm._request_windows.get(tenant, [])))
    return jsonify(
        {
            "uptime": uptime,
            "pending_patches": _pending_patches(),
            "cost_today": tenant_cost,
            "rate_remaining": remaining,
        }
    )


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), mimetype="text/plain")


if __name__ == "__main__":  # pragma: no cover - CLI
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

