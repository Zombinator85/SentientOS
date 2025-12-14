"""Deterministic doctrine digest helpers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def _normalize_doctrine(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines)


def compute_doctrine_digest(path: Path) -> str:
    """
    Return a deterministic hash of DOCTRINE.md.
    Must ignore:
      - trailing whitespace
      - line-ending differences
    Must include:
      - full textual content
    """

    text = path.read_text(encoding="utf-8")
    normalized = _normalize_doctrine(text)
    return sha256(normalized.encode("utf-8")).hexdigest()


__all__ = ["compute_doctrine_digest"]
