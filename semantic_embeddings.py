"""Semantic embedding utilities for SentientOS memory systems.

This module attempts to load a high quality sentence embedding model from
``sentence_transformers``. When the optional dependency is unavailable (which is
common in constrained test environments) the functions fall back to the
existing deterministic hashing strategy so the rest of the system continues to
operate.

The helper exposes a single :func:`encode` entry point that accepts a sequence
of strings and returns lists of floats suitable for similarity search. The
interface intentionally mirrors the lightweight expectations of
``memory_manager`` to keep existing call-sites unchanged.
"""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - gracefully handle missing package
    SentenceTransformer = None  # type: ignore[assignment]

_MODEL_NAME = os.getenv("SENTIENTOS_EMBED_MODEL", "all-MiniLM-L6-v2")
_MODEL: SentenceTransformer | None = None  # type: ignore[name-defined]
_LOCK = threading.Lock()


def _load_model() -> SentenceTransformer | None:  # pragma: no cover - lazy loader
    """Return the shared sentence transformer instance if available."""

    global _MODEL
    if SentenceTransformer is None:
        return None
    if _MODEL is None:
        with _LOCK:
            if _MODEL is None:
                _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def _fallback(text: str) -> List[float]:
    """Return a deterministic pseudo-embedding for ``text``.

    The fallback mirrors the legacy behaviour from ``memory_manager`` so that
    downstream code continues to work even without the ML dependency.
    """

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:64]]


def encode(texts: Iterable[str]) -> List[List[float]]:
    """Encode ``texts`` into dense vector representations.

    Parameters
    ----------
    texts:
        Strings that should be embedded.

    Returns
    -------
    list[list[float]]
        Dense embeddings compatible with cosine similarity search.
    """

    texts = list(texts)
    model = _load_model()
    if not texts:
        return []
    if model is None:  # fall back to deterministic hashing strategy
        return [_fallback(t) for t in texts]
    vectors = model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
    return [list(map(float, vec)) for vec in vectors]


def embedding_dim() -> int:
    """Return the embedding dimensionality for downstream sanity checks."""

    model = _load_model()
    if model is None:
        return len(_fallback("sentientos"))
    return int(getattr(model, "get_sentence_embedding_dimension")())


__all__ = ["encode", "embedding_dim"]

