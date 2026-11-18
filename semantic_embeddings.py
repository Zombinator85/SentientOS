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
import json
import math
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping

_MODEL_NAME = os.getenv("SENTIENTOS_EMBED_MODEL", "all-MiniLM-L6-v2")
_MODEL: Any = None
SentenceTransformer: Any = None
_LOCK = threading.Lock()
_SEMANTIC_MODELS: dict[tuple[str, str], Any] = {}


def _load_model() -> Any:  # pragma: no cover - lazy loader
    """Return the shared sentence transformer instance if available."""

    global _MODEL, SentenceTransformer
    if SentenceTransformer is None:
        try:
            from sentence_transformers import SentenceTransformer as model_type  # type: ignore[import-untyped]
        except Exception:
            return None
        SentenceTransformer = model_type
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


@dataclass(frozen=True)
class SemanticEmbeddingResult:
    """Pinned CPU embeddings with identity suitable for retrieval lineage."""

    identity: Mapping[str, str]
    identity_digest: str
    vectors: tuple[tuple[float, ...], ...]


def _load_pinned_cpu_model(model_id: str, revision: str) -> Any | None:
    """Load only a locally cached, pinned SentenceTransformer on CPU."""

    global SentenceTransformer
    if SentenceTransformer is None:
        try:
            from sentence_transformers import SentenceTransformer as model_type  # type: ignore[import-untyped]
        except Exception:
            return None
        SentenceTransformer = model_type
    if SentenceTransformer is None:
        return None
    key = (model_id, revision)
    if key not in _SEMANTIC_MODELS:
        with _LOCK:
            if key not in _SEMANTIC_MODELS:
                try:
                    _SEMANTIC_MODELS[key] = SentenceTransformer(
                        model_id, revision=revision, local_files_only=True,
                        device="cpu", trust_remote_code=False)
                except Exception:
                    return None
    return _SEMANTIC_MODELS[key]


def encode_semantic(texts: Iterable[str], *, model_id: str,
        revision: str) -> SemanticEmbeddingResult | None:
    """Return true semantic vectors, or ``None`` without a semantic fallback.

    This opt-in API requires an immutable 40-character model revision, reads
    only files already present in the local model cache, and pins both model
    loading and encoding to CPU. Unlike :func:`encode`, it never substitutes
    deterministic hash vectors when the model is unavailable.
    """

    try:
        values = list(texts)
    except Exception:
        return None
    if (not isinstance(model_id, str) or not model_id or len(model_id) > 256
            or not isinstance(revision, str)
            or re.fullmatch(r"[0-9a-f]{40}", revision) is None
            or len(values) > 257
            or any(not isinstance(value, str) or not value or len(value) > 4000
                for value in values)):
        return None
    if not values:
        return None
    model = _load_pinned_cpu_model(model_id, revision)
    if model is None:
        return None
    try:
        raw_vectors = model.encode(values, normalize_embeddings=True,
            convert_to_numpy=True, device="cpu")
        vectors = tuple(tuple(float(value) for value in vector)
            for vector in raw_vectors)
    except Exception:
        return None
    if (len(vectors) != len(values) or not vectors
            or not vectors[0] or any(len(vector) != len(vectors[0])
                or any(not math.isfinite(value) for value in vector)
                or not 0.95 <= math.sqrt(sum(value * value for value in vector)) <= 1.05
                for vector in vectors)):
        return None
    identity = {"schema_version": "sentientos.semantic_embedder_identity:v1",
        "provider": "sentence-transformers", "model_id": model_id,
        "revision": revision, "device": "cpu"}
    identity_digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return SemanticEmbeddingResult(identity, identity_digest, vectors)


__all__ = ["SemanticEmbeddingResult", "encode", "encode_semantic", "embedding_dim"]
