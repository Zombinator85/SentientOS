"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import json
from pathlib import Path
from fastapi import FastAPI
from typing import Any, Callable, TypeVar, cast

app = FastAPI(title="Federation API")
Handler = TypeVar("Handler", bound=Callable[..., object])
typed_get = cast(Callable[[str], Callable[[Handler], Handler]], app.get)


@typed_get("/federation")
def get_federation(limit: int = 10) -> list[dict[str, Any]]:
    path = Path("logs/federation_log.jsonl")
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    payload: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            payload.append(parsed)
    return payload
