from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

BRIDGE_DIR = Path(os.getenv("NEOS_BRIDGE_DIR", "C:/SentientOS/neos"))
BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = Path(os.getenv("NEOS_SCENE_LOG", "logs/neos_scene_pipeline.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def generate_scene(mood: str, blessing: str) -> Dict[str, Any]:
    scene = {
        "timestamp": datetime.utcnow().isoformat(),
        "mood": mood,
        "blessing": blessing,
        "rooms": [{"name": "sanctuary", "lighting": mood}],
    }
    file_path = BRIDGE_DIR / f"scene_{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
    file_path.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(scene) + "\n")
    return scene


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Sanctuary Scene Pipeline")
    ap.add_argument("mood")
    ap.add_argument("blessing")
    args = ap.parse_args()
    scene = generate_scene(args.mood, args.blessing)
    print(json.dumps(scene, indent=2))


if __name__ == "__main__":
    main()
