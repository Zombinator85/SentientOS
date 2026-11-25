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
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, List, Mapping

_MODEL_NAME = os.getenv("SENTIENTOS_EMBED_MODEL", "all-MiniLM-L6-v2")
_MODEL: Any = None
SentenceTransformer: Any = None
_LOCK = threading.Lock()
MAX_CACHED_SEMANTIC_MODELS = 2
MAX_CONCURRENT_SEMANTIC_ENCODINGS = 2
SEMANTIC_ENCODING_QUEUE_TIMEOUT_SECONDS = 30
MAX_SEMANTIC_EMBEDDING_INPUTS = 257
_SEMANTIC_ENCODER_SEMAPHORE = threading.BoundedSemaphore(
    MAX_CONCURRENT_SEMANTIC_ENCODINGS)
_SEMANTIC_MODELS: OrderedDict[tuple[str, str], Any] = OrderedDict()
MAX_SEMANTIC_VECTOR_DIMENSION = 1024
SEMANTIC_EMBEDDING_STATUSES = frozenset({
    "available", "available_dimension_observed", "invalid_input_iterable",
    "request_invalid", "empty_input", "encoder_queue_timeout",
    "model_unavailable", "model_dimension_unavailable",
    "model_dimension_out_of_bounds", "encoded_vector_shape_invalid",
    "encoding_failed", "encoded_vector_values_invalid"})
_SEMANTIC_ATTEMPT_STATUS: ContextVar[str | None] = ContextVar(
    "sentientos_semantic_embedding_attempt_status", default=None)


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

    def __post_init__(self) -> None:
        identity_fields = {"schema_version", "provider", "model_id",
            "revision", "device"}
        if (not isinstance(self.identity, Mapping)
                or set(self.identity) != identity_fields):
            raise ValueError("semantic_embedding_result_identity_invalid")
        identity = dict(self.identity)
        if (identity.get("schema_version") !=
                "sentientos.semantic_embedder_identity:v1"
                or identity.get("provider") != "sentence-transformers"
                or not isinstance(identity.get("model_id"), str)
                or not identity["model_id"] or len(identity["model_id"]) > 256
                or not isinstance(identity.get("revision"), str)
                or re.fullmatch(r"[0-9a-f]{40}", identity["revision"]) is None
                or identity.get("device") != "cpu"):
            raise ValueError("semantic_embedding_result_identity_invalid")
        expected_digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        if self.identity_digest != expected_digest:
            raise ValueError("semantic_embedding_result_identity_digest_invalid")
        vectors = self.vectors
        if (not isinstance(vectors, tuple) or not vectors
                or len(vectors) > MAX_SEMANTIC_EMBEDDING_INPUTS
                or not isinstance(vectors[0], tuple)
                or not 1 <= len(vectors[0]) <= MAX_SEMANTIC_VECTOR_DIMENSION):
            raise ValueError("semantic_embedding_result_vectors_invalid")
        dimension = len(vectors[0])
        for vector in vectors:
            if (not isinstance(vector, tuple) or len(vector) != dimension
                    or any(type(value) is not float or not math.isfinite(value)
                        for value in vector)
                    or not 0.95 <= math.sqrt(sum(value * value
                        for value in vector)) <= 1.05):
                raise ValueError("semantic_embedding_result_vectors_invalid")
        object.__setattr__(self, "identity", MappingProxyType(identity))


@dataclass(frozen=True)
class SemanticEmbeddingAttempt:
    """Bounded outcome code for semantic retrieval, with no exception details."""

    status: str
    result: SemanticEmbeddingResult | None

    def __post_init__(self) -> None:
        if (not isinstance(self.status, str)
                or self.status not in SEMANTIC_EMBEDDING_STATUSES):
            raise ValueError("semantic_embedding_status_invalid")
        successful = self.status in {
            "available", "available_dimension_observed"}
        if ((successful and not isinstance(
                    self.result, SemanticEmbeddingResult))
                or (not successful and self.result is not None)):
            raise ValueError("semantic_embedding_status_result_mismatch")


def _load_pinned_cpu_model(model_id: str, revision: str) -> Any | None:
    """Load only a locally cached, pinned SentenceTransformer on CPU."""

    global SentenceTransformer, _SEMANTIC_MODELS
    if SentenceTransformer is None:
        try:
            from sentence_transformers import SentenceTransformer as model_type  # type: ignore[import-untyped]
        except Exception:
            return None
        SentenceTransformer = model_type
    if SentenceTransformer is None:
        return None
    key = (model_id, revision)
    with _LOCK:
        if not isinstance(_SEMANTIC_MODELS, OrderedDict):
            _SEMANTIC_MODELS = OrderedDict(_SEMANTIC_MODELS)
        cached = _SEMANTIC_MODELS.get(key)
        if cached is not None:
            _SEMANTIC_MODELS.move_to_end(key)
            return cached
        try:
            model = SentenceTransformer(model_id, revision=revision,
                local_files_only=True, device="cpu", trust_remote_code=False)
        except Exception:
            return None
        if model is None:
            return None
        _SEMANTIC_MODELS[key] = model
        _SEMANTIC_MODELS.move_to_end(key)
        while len(_SEMANTIC_MODELS) > MAX_CACHED_SEMANTIC_MODELS:
            _SEMANTIC_MODELS.popitem(last=False)
        return model


def encode_semantic(texts: Iterable[str], *, model_id: str,
        revision: str) -> SemanticEmbeddingResult | None:
    """Return true semantic vectors, or ``None`` without a semantic fallback.

    This opt-in API requires an immutable 40-character model revision, reads
    only files already present in the local model cache, and pins both model
    loading and encoding to CPU. Unlike :func:`encode`, it never substitutes
    deterministic hash vectors when the model is unavailable.
    """

    _SEMANTIC_ATTEMPT_STATUS.set(None)
    attempt = encode_semantic_with_status(texts, model_id=model_id,
        revision=revision)
    _SEMANTIC_ATTEMPT_STATUS.set(attempt.status)
    return attempt.result


def clear_semantic_embedding_attempt_status() -> None:
    """Clear this execution context's prior status before a new call."""
    _SEMANTIC_ATTEMPT_STATUS.set(None)


def get_semantic_embedding_attempt_status() -> str | None:
    """Return the latest status produced by :func:`encode_semantic` here."""
    return _SEMANTIC_ATTEMPT_STATUS.get()


def encode_semantic_with_status(texts: Iterable[str], *, model_id: str,
        revision: str) -> SemanticEmbeddingAttempt:
    """Return semantic output plus a stable status for retrieval evidence."""
    if (not isinstance(model_id, str) or not model_id or len(model_id) > 256
            or not isinstance(revision, str)
            or re.fullmatch(r"[0-9a-f]{40}", revision) is None):
        return SemanticEmbeddingAttempt("request_invalid", None)
    if isinstance(texts, (str, bytes, bytearray)):
        return SemanticEmbeddingAttempt("invalid_input_iterable", None)
    try:
        iterator = iter(texts)
        values = []
        for _ in range(MAX_SEMANTIC_EMBEDDING_INPUTS + 1):
            try:
                value = next(iterator)
            except StopIteration:
                break
            if len(values) == MAX_SEMANTIC_EMBEDDING_INPUTS:
                return SemanticEmbeddingAttempt("request_invalid", None)
            if (not isinstance(value, str) or not value or len(value) > 4000):
                return SemanticEmbeddingAttempt("request_invalid", None)
            values.append(value)
    except Exception:
        return SemanticEmbeddingAttempt("invalid_input_iterable", None)
    if not values:
        return SemanticEmbeddingAttempt("empty_input", None)
    if not _SEMANTIC_ENCODER_SEMAPHORE.acquire(
            timeout=SEMANTIC_ENCODING_QUEUE_TIMEOUT_SECONDS):
        return SemanticEmbeddingAttempt("encoder_queue_timeout", None)
    try:
        return _encode_semantic_values(values, model_id=model_id,
            revision=revision)
    finally:
        _SEMANTIC_ENCODER_SEMAPHORE.release()


def _encode_semantic_values(values: list[str], *, model_id: str,
        revision: str) -> SemanticEmbeddingAttempt:
    model = _load_pinned_cpu_model(model_id, revision)
    if model is None:
        return SemanticEmbeddingAttempt("model_unavailable", None)
    try:
        dimension_getter = getattr(model, "get_embedding_dimension", None)
        if not callable(dimension_getter):
            dimension_getter = getattr(model,
                "get_sentence_embedding_dimension", None)
    except Exception:
        return SemanticEmbeddingAttempt("model_dimension_unavailable", None)
    declared_dimension = None
    if callable(dimension_getter):
        try:
            declared_dimension = dimension_getter()
        except Exception:
            return SemanticEmbeddingAttempt("model_dimension_unavailable", None)
        if declared_dimension is None:
            return SemanticEmbeddingAttempt("model_dimension_unavailable", None)
        if (type(declared_dimension) is not int
                or not 1 <= declared_dimension <=
                    MAX_SEMANTIC_VECTOR_DIMENSION):
            return SemanticEmbeddingAttempt("model_dimension_out_of_bounds", None)
    try:
        raw_vectors = model.encode(values, normalize_embeddings=True,
            convert_to_numpy=True, device="cpu")
    except Exception:
        return SemanticEmbeddingAttempt("encoding_failed", None)
    try:
        if len(raw_vectors) != len(values) or len(raw_vectors) == 0:
            return SemanticEmbeddingAttempt("encoded_vector_shape_invalid", None)
        dimension = len(raw_vectors[0])
        if ((declared_dimension is not None
                and dimension != declared_dimension)
                or not 1 <= dimension <= MAX_SEMANTIC_VECTOR_DIMENSION
                or any(len(vector) != dimension for vector in raw_vectors)):
            return SemanticEmbeddingAttempt("encoded_vector_shape_invalid", None)
    except Exception:
        return SemanticEmbeddingAttempt("encoded_vector_shape_invalid", None)
    try:
        vectors = tuple(tuple(float(value) for value in vector)
            for vector in raw_vectors)
    except Exception:
        return SemanticEmbeddingAttempt("encoded_vector_values_invalid", None)
    if (len(vectors) != len(values) or not vectors
            or not vectors[0] or any(any(not math.isfinite(value)
                for value in vector)
                or not 0.95 <= math.sqrt(sum(value * value for value in vector)) <= 1.05
                for vector in vectors)):
        return SemanticEmbeddingAttempt("encoded_vector_values_invalid", None)
    identity = {"schema_version": "sentientos.semantic_embedder_identity:v1",
        "provider": "sentence-transformers", "model_id": model_id,
        "revision": revision, "device": "cpu"}
    identity_digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    status = ("available" if declared_dimension is not None
        else "available_dimension_observed")
    return SemanticEmbeddingAttempt(status,
        SemanticEmbeddingResult(identity, identity_digest, vectors))


__all__ = ["MAX_CACHED_SEMANTIC_MODELS", "MAX_SEMANTIC_EMBEDDING_INPUTS",
    "MAX_CONCURRENT_SEMANTIC_ENCODINGS", "MAX_SEMANTIC_VECTOR_DIMENSION",
    "SEMANTIC_EMBEDDING_STATUSES", "SEMANTIC_ENCODING_QUEUE_TIMEOUT_SECONDS",
    "SemanticEmbeddingAttempt", "SemanticEmbeddingResult", "encode",
    "clear_semantic_embedding_attempt_status", "encode_semantic",
    "encode_semantic_with_status", "embedding_dim",
    "get_semantic_embedding_attempt_status"]
