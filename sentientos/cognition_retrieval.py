"""Shared lexical normalization for bounded cognition context selection."""
from __future__ import annotations

import re


_QUERY_STOP_WORDS = frozenset((
    "a", "about", "after", "again", "all", "also", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "between", "both",
    "but", "by", "can", "could", "did", "do", "does", "doing", "down", "each",
    "few", "for", "from", "had", "has", "have", "he", "her", "here", "hers",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just",
    "learn", "like", "may", "me", "might", "more", "most", "much", "must", "my",
    "no", "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other",
    "our", "ours", "out", "over", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "then", "there", "these",
    "they", "this", "those", "through", "to", "under", "until", "up", "us", "very",
    "was", "we", "were", "what", "when", "where", "whether", "which", "while", "who",
    "whom", "why", "will", "with", "would", "you", "your", "yours"))


def cognition_query_terms(text: str) -> set[str]:
    """Return normalized topic terms, excluding question framing and stop words."""
    terms: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9]{3,}", text.casefold()):
        if token in _QUERY_STOP_WORDS:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        terms.add(token)
    return terms

