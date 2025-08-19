"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import time
from pathlib import Path
from typing import Iterable, Tuple

import requests  # type: ignore[import-untyped]
import yaml

CONFIG_PATH = Path("config/federation.yaml")
LOG_PATH = Path("logs/federation_log.jsonl")


def load_peers(config_path: Path = CONFIG_PATH) -> list[str]:
    """Return list of peer presence URLs from config."""
    if not config_path.exists():
        return []
    try:
        data = yaml.safe_load(config_path.read_text()) or {}
    except Exception:
        return []
    return [p.get("url", "") for p in data.get("peers", []) if p.get("url")]


def load_seen(log_path: Path = LOG_PATH) -> set[Tuple[str, str]]:
    """Load existing dialogue_id/source pairs to avoid duplicates."""
    seen: set[Tuple[str, str]] = set()
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            did = data.get("dialogue_id")
            src = data.get("source")
            if did and src:
                seen.add((did, src))
    return seen


def poll_peers(
    peers: Iterable[str], log_path: Path = LOG_PATH, seen: set[Tuple[str, str]] | None = None
) -> None:
    """Fetch presence from peers and append new entries to the federation log."""
    if seen is None:
        seen = load_seen(log_path)
    new_lines: list[str] = []
    for url in peers:
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            items = resp.json()
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            did = item.get("dialogue_id")
            if not did:
                continue
            key = (did, url)
            if key in seen:
                continue
            seen.add(key)
            entry = dict(item)
            entry["source"] = url
            new_lines.append(json.dumps(entry))
    if new_lines:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for line in new_lines:
                fh.write(line + "\n")


def main() -> None:
    peers = load_peers()
    seen = load_seen()
    while True:
        poll_peers(peers, LOG_PATH, seen)
        time.sleep(10)


if __name__ == "__main__":
    main()
