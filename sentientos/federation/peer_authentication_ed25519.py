"""Optional Ed25519 verification backend for authenticated Federation peers.

This module verifies signatures only. Peer selection, replay ownership, trust
catalog pins, freshness, and all authority decisions remain separate.
"""
from __future__ import annotations

import base64
import importlib
import re
from typing import Any, Tuple, final

from .peer_authentication import ED25519_ALGORITHM

_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
_BACKEND_ERROR = "federation_peer_ed25519_backend_unavailable"


class FederationPeerSignatureBackendUnavailable(RuntimeError):
    """The optional Ed25519 verification dependency cannot operate."""


def _load_cryptography() -> Tuple[Any, Any]:
    try:
        exceptions = importlib.import_module("cryptography.exceptions")
        ed25519 = importlib.import_module(
            "cryptography.hazmat.primitives.asymmetric.ed25519"
        )
        return exceptions.InvalidSignature, ed25519.Ed25519PublicKey
    except (ImportError, AttributeError) as exc:
        raise FederationPeerSignatureBackendUnavailable(_BACKEND_ERROR) from exc


def _decode_public_key(value: object) -> bytes | None:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        return None
    try:
        decoded = base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, ValueError):
        return None
    if (
        len(decoded) != 32
        or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value
    ):
        return None
    return decoded


def _decode_signature(value: object) -> bytes | None:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        return None
    try:
        decoded = base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, ValueError):
        return None
    if (
        len(decoded) != 64
        or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value
    ):
        return None
    return decoded


@final
class CryptographyEd25519FederationPeerSignatureVerifier:
    """Verify Federation peer signatures with a public Ed25519 key only."""

    __slots__ = ()

    def verify(
        self,
        *,
        algorithm: str,
        public_key: str,
        payload: bytes,
        signature: str,
    ) -> bool:
        if algorithm != ED25519_ALGORITHM or not isinstance(payload, bytes):
            return False
        public_bytes = _decode_public_key(public_key)
        signature_bytes = _decode_signature(signature)
        if public_bytes is None or signature_bytes is None:
            return False
        try:
            invalid_signature, public_key_type = _load_cryptography()
        except FederationPeerSignatureBackendUnavailable:
            raise
        except Exception as exc:
            raise FederationPeerSignatureBackendUnavailable(_BACKEND_ERROR) from exc
        try:
            verifier = public_key_type.from_public_bytes(public_bytes)
            verifier.verify(signature_bytes, payload)
        except invalid_signature:
            return False
        except (TypeError, ValueError):
            return False
        except Exception as exc:
            raise FederationPeerSignatureBackendUnavailable(_BACKEND_ERROR) from exc
        return True


__all__ = [
    "CryptographyEd25519FederationPeerSignatureVerifier",
    "FederationPeerSignatureBackendUnavailable",
]
