"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

from fastapi import FastAPI
from pydantic import BaseModel
import yaml
from wdm.runner import run_wdm

app = FastAPI(title="WDM API")


class WDMReq(BaseModel):
    seed: str
    context: dict = {}


@app.post("/wdm/start")
def start(req: WDMReq):
    with open("config/wdm.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return run_wdm(req.seed, req.context, cfg)

