"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

import json
import time
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

require_admin_banner()
require_lumos_approval()

try:  # pragma: no cover - best effort
    from transformers import pipeline

    MODEL = pipeline("text-generation", model="distilgpt2")
except Exception:  # pragma: no cover - best effort
    MODEL = None


LOG_PATH = Path("relay_logs.jsonl")
app = FastAPI()


class RelayRequest(BaseModel):
    task: str
    context: str = ""


@app.post("/relay")
def relay(req: RelayRequest) -> dict:
    prompt = f"{req.context}\n{req.task}".strip()
    if MODEL is not None:
        try:  # pragma: no cover - best effort
            result = MODEL(prompt, max_new_tokens=50)
            output = result[0]["generated_text"]
        except Exception:  # pragma: no cover - best effort
            output = f"Echo: {req.task}"
    else:
        output = f"Echo: {req.task}"
    response = {"output": output}
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "ts": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "request": req.dict(),
                    "response": response,
                }
            )
            + "\n"
        )
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)

