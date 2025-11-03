"""Admin API exposing autonomy status and metrics."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .autonomy import AutonomyRuntime
from .config import load_runtime_config
from .logging_middleware import RedactingLoggingMiddleware
from .slo import evaluate as evaluate_slos
from .slo import to_dict as slo_to_dict
from .slo import to_prometheus as slo_to_prometheus

RUNTIME = AutonomyRuntime.from_config(load_runtime_config())
APP = FastAPI()
app = APP

PRIVACY = RUNTIME.privacy
APP.add_middleware(RedactingLoggingMiddleware, redactor=PRIVACY.redactor)


@APP.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    is_admin = path.startswith("/admin")
    if is_admin:
        RUNTIME.metrics.increment("sos_admin_requests_total")
    try:
        response = await call_next(request)
    except Exception:
        if is_admin:
            RUNTIME.metrics.increment("sos_admin_failures_total")
        raise
    if is_admin:
        elapsed_ms = (time.perf_counter() - start) * 1000
        RUNTIME.metrics.observe("sos_admin_latency_ms", elapsed_ms)
    return response


@APP.get("/admin/status")
def admin_status() -> JSONResponse:
    status = RUNTIME.status()
    modules = status.modules
    slo_statuses = evaluate_slos(RUNTIME.metrics, modules)
    degraded = [
        name
        for name, module in modules.items()
        if isinstance(module, dict) and module.get("status") not in {"healthy", "disabled"}
    ]
    payload = {
        "overall": status.overall_state(),
        "modules": modules,
        "slos": slo_to_dict(slo_statuses),
    }
    if degraded:
        payload["degraded_modules"] = degraded
    if any(not entry.ok for entry in slo_statuses):
        payload["slo_breaches"] = [
            entry.definition.name for entry in slo_statuses if not entry.ok
        ]
    return JSONResponse(payload)


@APP.get("/admin/metrics")
def admin_metrics() -> PlainTextResponse:
    status = RUNTIME.status()
    slo_statuses = evaluate_slos(RUNTIME.metrics, status.modules)
    base_metrics = RUNTIME.export_metrics()
    slo_metrics = slo_to_prometheus(slo_statuses)
    text = "\n".join(filter(None, [base_metrics, slo_metrics]))
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4")


__all__ = ["APP", "app", "admin_status", "admin_metrics", "RUNTIME"]
