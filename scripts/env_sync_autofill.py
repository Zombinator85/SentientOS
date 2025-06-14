"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Ensure required .env keys exist, filling defaults if missing."""

import datetime
import json
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
ENV_LOG = LOG_DIR / "env_autofill_log.jsonl"


def autofill_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8")
        lines = text.splitlines()
    else:
        lines = []
    added = {}
    mapping = {
        "OPENAI_API_KEY": "",
        "MODEL_SLUG": "openai/gpt-4o",
        "SYSTEM_PROMPT": "You are Lumos...",
        "ENABLE_TTS": "true",
        "TTS_ENGINE": "pyttsx3",
    }
    keys = {ln.split("=", 1)[0] for ln in lines if "=" in ln and not ln.strip().startswith("#")}
    for k, v in mapping.items():
        if k not in keys:
            lines.append(f"{k}={v}")
            added[k] = v
    if added:
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "added": added,
        }
        with ENV_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def main() -> None:  # pragma: no cover - CLI
    autofill_env()
    print(".env synchronized")


if __name__ == "__main__":
    main()
