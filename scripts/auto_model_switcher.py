from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from typing import Dict, List

import yaml

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from scripts.auto_approve import is_auto_approve

# Switch models based on remaining quotas and configured fallbacks.

USAGE_FILE = Path("usage_monitor.jsonl")
OUTPUT_FILE = Path("current_model.json")


def load_usage(path: Path) -> Dict[str, dict]:
    """Load the latest usage entry per model."""
    data: Dict[str, dict] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        data[rec.get("model", "")] = rec
    return data


def pick_model(chain: List[str], usage: Dict[str, dict], buffer: float = 0.15) -> str:
    """Return the first model in chain with enough remaining quota."""
    best = chain[0]
    best_ratio = -1.0
    for model in chain:
        info = usage.get(model)
        if not info:
            continue
        total = info.get("messages_used", 0) + info.get("messages_remaining", 0)
        if total <= 0:
            continue
        ratio = info["messages_remaining"] / total
        if ratio >= buffer:
            return model
        if ratio > best_ratio:
            best_ratio = ratio
            best = model
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description="Automatically switch models")
    parser.add_argument("--config", type=Path, default="model_switcher.yml", help="Task to model mapping YAML")
    parser.add_argument("--usage-json", type=Path, default=USAGE_FILE, help="Usage monitor file")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Config not found: {args.config}")
        return

    with args.config.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    usage = load_usage(args.usage_json)
    result = {}
    for task, models in config.items():
        if isinstance(models, str):
            models = [models]
        result[task] = pick_model(models, usage)

    OUTPUT_FILE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
