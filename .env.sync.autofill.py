"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Sync `.env` with required keys, adding safe defaults if missing."""

import datetime
import json
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
ENV_LOG = LOG_DIR / "env_autofill_log.jsonl"

REQUIRED_KEYS = {
    "OPENAI_API_KEY": "",
    "MODEL_SLUG": "openai/gpt-4o",
    "SYSTEM_PROMPT": "You are Lumos...",
    "ENABLE_TTS": "true",
    "TTS_ENGINE": "pyttsx3",
    "MAX_LOG_SIZE_MB": "10",
    "LOG_ROTATE_WEEKLY": "true",
}


def autofill_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    existing = {ln.split("=", 1)[0] for ln in lines if "=" in ln and not ln.strip().startswith("#")}
    missing = [k for k in REQUIRED_KEYS if k not in existing]
    if not missing:
        return
    for key in missing:
        lines.append(f"{key}={REQUIRED_KEYS[key]}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entry = {
        "event_type": "env_autofill",
        "missing_keys": missing,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    with ENV_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:  # pragma: no cover - CLI
    autofill_env()
    print("Environment synchronized")


if __name__ == "__main__":
    main()
