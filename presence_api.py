"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

from fastapi import FastAPI
import json
from pathlib import Path

app = FastAPI(title="Presence API")

@app.get("/presence")
def get_presence(limit: int = 10):
    path = Path("logs/presence.jsonl")
    if not path.exists():
        return []
    lines = path.read_text().splitlines()[-limit:]
    return [json.loads(l) for l in lines if l.strip()]
