"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from fastapi import FastAPI
import json
from pathlib import Path

app = FastAPI(title="Migration Ledger API")

LEDGER = Path("logs/migration_ledger.jsonl")


@app.get("/ledger")
def get_ledger(limit: int = 10):
    if not LEDGER.exists():
        return []
    lines = LEDGER.read_text().splitlines()[-limit:]
    return [json.loads(l) for l in lines if l.strip()]

