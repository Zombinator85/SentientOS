import os
import time
import hashlib
from collections import defaultdict, deque
from typing import Dict

from flask import g, request, abort

TENANT_DAILY_LIMIT = float(os.getenv("TENANT_DAILY_LIMIT", "2"))
TENANT_RATE_LIMIT = int(os.getenv("TENANT_RATE_LIMIT", "60"))
TENANT_RATE_WINDOW = int(os.getenv("TENANT_RATE_WINDOW", "60"))

_keys: Dict[str, str] | None = None
_request_windows: Dict[str, deque[float]] = defaultdict(deque)
_daily_cost: Dict[str, float] = defaultdict(float)


def _load_keys() -> Dict[str, str]:
    path = os.getenv("SENTIENTOS_KEYS_FILE", "keys.yaml")
    if not os.path.exists(path):
        return {}
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {str(k): str(v) for k, v in data.items()}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _ensure_keys_loaded() -> None:
    global _keys
    if _keys is None:
        _keys = _load_keys()


def get_tenant_id() -> str:
    _ensure_keys_loaded()
    allow_anon = os.getenv("SENTIENTOS_ALLOW_ANON") == "1"
    auth = request.headers.get("Authorization")
    if not auth:
        if allow_anon:
            return request.headers.get("X-Sentient-Tenant", "public")
        abort(401)
    if not auth.startswith("Bearer "):
        abort(401)
    token = auth.split(" ", 1)[1]
    if _keys:
        for tenant, thash in _keys.items():
            if _hash(token) == thash:
                return tenant
    abort(401)


def tenant_context() -> None:
    tenant_id = request.headers.get("X-Sentient-Tenant", "public")
    g.tenant_id = tenant_id


def rate_limit() -> None:
    tenant = getattr(g, "tenant_id", "public")
    now = time.time()
    window = _request_windows[tenant]
    while window and now - window[0] > TENANT_RATE_WINDOW:
        window.popleft()
    if len(window) >= TENANT_RATE_LIMIT:
        abort(429)
    window.append(now)


def add_cost(amount: float, tenant: str | None = None) -> None:
    tenant = tenant or getattr(g, "tenant_id", "public")
    _daily_cost[tenant] += amount


def check_cost_limit() -> None:
    tenant = getattr(g, "tenant_id", "public")
    if _daily_cost[tenant] > TENANT_DAILY_LIMIT:
        abort(503)


def tenant_requests_metric() -> Dict[str, float]:
    return {t: float(len(w)) for t, w in _request_windows.items()}


def tenant_cost_metric() -> Dict[str, float]:
    return dict(_daily_cost)
