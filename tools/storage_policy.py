"""Storage hygiene helpers used by SentientOS tests."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass
class StoragePolicyConfig:
    digest_dir: Path
    highlight_dir: Path
    max_digests: int = 7


def rotate_text_digests(policy: StoragePolicyConfig, entries: Iterable[str]) -> Path:
    policy.digest_dir.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    path = policy.digest_dir / f"daily-{today}.md"
    path.write_text("\n".join(entries), encoding="utf-8")
    _prune(policy.digest_dir, policy.max_digests)
    return path


def stash_highlight(policy: StoragePolicyConfig, filename: str, content: bytes) -> Path:
    policy.highlight_dir.mkdir(parents=True, exist_ok=True)
    today_dir = policy.highlight_dir / _dt.date.today().isoformat()
    today_dir.mkdir(parents=True, exist_ok=True)
    path = today_dir / filename
    path.write_bytes(content)
    return path


def _prune(directory: Path, keep: int) -> None:
    files = sorted(directory.glob("*.md"))
    for path in files[:-keep]:
        try:
            path.unlink()
        except FileNotFoundError:  # pragma: no cover - defensive
            continue


__all__ = ["StoragePolicyConfig", "rotate_text_digests", "stash_highlight"]

