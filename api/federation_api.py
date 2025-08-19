"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import json
from pathlib import Path
from fastapi import FastAPI

app = FastAPI(title="Federation API")


@app.get("/federation")
def get_federation(limit: int = 10):
    path = Path("logs/federation_log.jsonl")
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(l) for l in lines if l.strip()]
