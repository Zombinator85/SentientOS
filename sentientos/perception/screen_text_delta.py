"""Bounded, ephemeral line-level deltas for consented OCR observations."""
from __future__ import annotations

from collections import Counter
import hashlib
import re
from typing import Any, Mapping

OCR_TEXT_LINE_DELTA_SCHEMA = "sentientos.ocr_text_line_delta:v1"
MAX_DELTA_LINES = 8
MAX_DELTA_LINE_CHARS = 160
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema_version", "previous_text_digest", "current_text_digest",
    "added_lines", "removed_lines", "truncated",
})


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_ocr_text_line_delta(previous_text: str, current_text: str) -> dict[str, Any]:
    """Return bounded added/removed OCR lines without assigning game semantics."""
    if (not isinstance(previous_text, str) or len(previous_text) > 1200
            or not isinstance(current_text, str) or len(current_text) > 1200):
        raise ValueError("ocr_text_line_delta_input_invalid")
    previous_lines = [line.strip() for line in previous_text.splitlines() if line.strip()]
    current_lines = [line.strip() for line in current_text.splitlines() if line.strip()]
    removed_counts = Counter(previous_lines) - Counter(current_lines)
    added_counts = Counter(current_lines) - Counter(previous_lines)

    def collect(lines: list[str], counts: Counter[str]) -> tuple[list[str], bool]:
        result: list[str] = []
        truncated = False
        for line in lines:
            if counts[line] <= 0:
                continue
            counts[line] -= 1
            if len(result) >= MAX_DELTA_LINES:
                truncated = True
                continue
            if len(line) > MAX_DELTA_LINE_CHARS:
                line = line[:MAX_DELTA_LINE_CHARS - 3] + "..."
                truncated = True
            result.append(line)
        return result, truncated

    removed, removed_truncated = collect(previous_lines, removed_counts)
    added, added_truncated = collect(current_lines, added_counts)
    return {
        "schema_version": OCR_TEXT_LINE_DELTA_SCHEMA,
        "previous_text_digest": _digest(previous_text),
        "current_text_digest": _digest(current_text),
        "added_lines": added,
        "removed_lines": removed,
        "truncated": removed_truncated or added_truncated,
    }


def validate_ocr_text_line_delta(delta: Any, *, current_text: str) -> dict[str, Any]:
    """Validate a delta before placing it in a prompt or durable provenance."""
    if not isinstance(delta, Mapping) or set(delta) != _FIELDS:
        raise ValueError("ocr_text_line_delta_shape_invalid")
    if (delta.get("schema_version") != OCR_TEXT_LINE_DELTA_SCHEMA
            or not isinstance(current_text, str) or len(current_text) > 1200
            or delta.get("current_text_digest") != _digest(current_text)
            or not isinstance(delta.get("previous_text_digest"), str)
            or _DIGEST.fullmatch(delta["previous_text_digest"]) is None
            or type(delta.get("truncated")) is not bool):
        raise ValueError("ocr_text_line_delta_contract_invalid")
    for field in ("added_lines", "removed_lines"):
        lines = delta.get(field)
        if (not isinstance(lines, list) or len(lines) > MAX_DELTA_LINES
                or any(not isinstance(line, str) or not line.strip()
                       or len(line) > MAX_DELTA_LINE_CHARS
                       or "\n" in line or "\r" in line for line in lines)):
            raise ValueError("ocr_text_line_delta_lines_invalid")
    return dict(delta)


__all__ = [
    "OCR_TEXT_LINE_DELTA_SCHEMA", "build_ocr_text_line_delta",
    "validate_ocr_text_line_delta",
]
