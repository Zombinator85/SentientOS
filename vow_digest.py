"""Canonical vow hashing utilities.

This module provides pure, deterministic helpers to load the canonical vow
artifact and compute its SHA-256 digest. It deliberately avoids any network or
mutation side effects so higher-level orchestration layers can rely on a stable
fingerprint.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def compute_vow_digest(text: str) -> str:
    """Return the SHA-256 hex digest of the provided vow text.

    The text is encoded as UTF-8 prior to hashing to ensure deterministic
    results across platforms.
    """

    return sha256(text.encode("utf-8")).hexdigest()


def load_canonical_vow() -> str:
    """Load the canonical vow text from the immutable local resource.

    The file is read relative to this module to avoid dependency on external
    paths or environment configuration. The content is returned exactly as
    stored with no normalization.
    """

    resource_path = Path(__file__).resolve().parent / "resources" / "canonical_vow.txt"
    return resource_path.read_text(encoding="utf-8")


def canonical_vow_digest() -> str:
    """Return the digest of the canonical vow resource."""

    return compute_vow_digest(load_canonical_vow())
