"""Admin API exposing autonomy status and metrics."""

from __future__ import annotations

import time

try:  # pragma: no cover - optional dependency
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, PlainTextResponse
except ModuleNotFoundError:  # pragma: no cover - test fallback
    class _SimpleResponse(dict):
        def __init__(self, content, status_code: int = 200, media_type: str = "application/json") -> None:
            super().__init__(content=content, status_code=status_code, media_type=media_type)

    class JSONResponse(_SimpleResponse):
        pass

    class PlainTextResponse(_SimpleResponse):
        pass

    class Request:  # type: ignore[override]
        def __init__(self, path: str = "/") -> None:
            class _URL:
                def __init__(self, path: str) -> None:
                    self.path = path

            self.url = _URL(path)

    class FastAPI:  # type: ignore[misc]
        def __init__(self) -> None:
            self._routes = {}

        def add_middleware(self, *args, **kwargs) -> None:
            return None

        def middleware(self, _type: str):
            def decorator(fn):
                self._routes.setdefault("middleware", []).append(fn)
                return fn

            return decorator

        def get(self, path: str):
            def decorator(fn):
                self._routes[path] = fn
                return fn

            return decorator

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


__all__ = ["APP", "app", "admin_status", "admin_metrics", "autonomy_status", "RUNTIME"]
