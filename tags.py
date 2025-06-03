"""SentientOS emotional tags module.

Reference: [docs/TAG_EXTENSION_GUIDE.md](docs/TAG_EXTENSION_GUIDE.md)
Templates and code patterns co-developed with OpenAI support.
"""
from __future__ import annotations
from typing import List, Dict

EMOTIONAL_TAGS: List[Dict[str, object]] = [
    {"tag": "joy", "color": "yellow", "reviewer": "core", "approved": True},
    {"tag": "sadness", "color": "blue", "reviewer": "core", "approved": True},
]


def list_tags() -> List[Dict[str, object]]:
    """Return the list of emotional tags.

    Example:
        >>> for t in list_tags():
        ...     print(t["tag"])
    """
    return EMOTIONAL_TAGS
