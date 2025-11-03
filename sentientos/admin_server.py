"""Admin API exposing autonomy status and metrics."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

from .autonomy import AutonomyRuntime
from .config import load_runtime_config

RUNTIME = AutonomyRuntime.from_config(load_runtime_config())
APP = FastAPI()
app = APP


@APP.get("/admin/status")
def admin_status() -> JSONResponse:
    status = RUNTIME.status()
    return JSONResponse({"overall": status.overall_state(), "modules": status.modules})


@APP.get("/admin/metrics")
def admin_metrics() -> PlainTextResponse:
    metrics = RUNTIME.export_metrics()
    return PlainTextResponse(metrics or "", media_type="text/plain; version=0.0.4")


__all__ = ["APP", "app", "admin_status", "admin_metrics", "RUNTIME"]
