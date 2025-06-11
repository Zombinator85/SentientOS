from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

TEMPLATES_DIR = Path("avatar_ritual_templates")
LOG_PATH = get_log_path("avatar_ritual_customizer.jsonl")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_customization(name: str, template: str) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "template": template,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def create(name: str, template: str) -> dict[str, Any]:
    """Save ritual customization stub."""
    path = TEMPLATES_DIR / f"{name}.json"
    data = {"template": template}
    path.write_text(json.dumps(data, indent=2))
    return log_customization(name, template)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Avatar ritual customizer")
    ap.add_argument("name")
    ap.add_argument("template")
    args = ap.parse_args()
    entry = create(args.name, args.template)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
