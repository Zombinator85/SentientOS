"""Admin API exposing autonomy status and metrics."""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from .fastapi_stub import FastAPI, JSONResponse, PlainTextResponse, Request

from daemon_autonomy_supervisor import DaemonAutonomySupervisor
from .autonomy import AutonomyRuntime
from .config import load_runtime_config
from .logging_middleware import RedactingLoggingMiddleware
from .slo import evaluate as evaluate_slos
from .slo import to_dict as slo_to_dict
from .slo import to_prometheus as slo_to_prometheus

RUNTIME = AutonomyRuntime.from_config(load_runtime_config())
SUPERVISOR = DaemonAutonomySupervisor(runtime=RUNTIME, auto_start=True)
APP = FastAPI()
app = APP

PRIVACY = RUNTIME.privacy
APP.add_middleware(RedactingLoggingMiddleware, redactor=PRIVACY.redactor)


@APP.middleware("http")
async def _metrics_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[object]],
) -> object:
    start = time.perf_counter()
    path = str(getattr(getattr(request, "url", object()), "path", ""))
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


@APP.get("/admin/status/autonomy")
def autonomy_status() -> JSONResponse:
    audit_summary = RUNTIME.audit_log.summary()
    social_status = RUNTIME.social.status()
    gui_status = RUNTIME.gui.status()
    payload = {
        "panic_active": RUNTIME.panic_active(),
        "recent_actions": audit_summary.get("recent", []),
        "action_totals": audit_summary.get("totals", {}),
        "blocked_recent": audit_summary.get("blocked_recent", 0),
        "council_votes": RUNTIME.council.history(10),
        "safety_budgets": {
            "social_budget_remaining": social_status.get("budget_remaining"),
            "gui": gui_status,
        },
    }
    return JSONResponse(payload)


@APP.get("/admin/status/supervisor")
def supervisor_status() -> JSONResponse:
    return JSONResponse(SUPERVISOR.status_report())


__all__ = [
    "APP",
    "app",
    "admin_status",
    "admin_metrics",
    "autonomy_status",
    "supervisor_status",
    "RUNTIME",
    "SUPERVISOR",
]
