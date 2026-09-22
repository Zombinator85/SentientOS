"""Optional production Ed25519 verification for root-issuer provenance.

This backend verifies only.  Trust selection and every authority-bearing decision
remain outside this module.
"""
from __future__ import annotations

import base64
import importlib
import re
from typing import Any, Callable, Tuple

from sentientos.causal_resource_principal_authentication import ED25519_ALGORITHM

_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
_BACKEND_ERROR = "ed25519_verification_backend_unavailable"


class Ed25519VerificationBackendUnavailable(RuntimeError):
    """The optional production verification dependency cannot operate."""


def _load_cryptography() -> Tuple[Any, Any]:
    """Load the runtime-extra backend without coupling core authentication to it."""
    try:
        exceptions = importlib.import_module("cryptography.exceptions")
        ed25519 = importlib.import_module(
            "cryptography.hazmat.primitives.asymmetric.ed25519"
        )
        return exceptions.InvalidSignature, ed25519.Ed25519PublicKey
    except (ImportError, AttributeError) as exc:
        raise Ed25519VerificationBackendUnavailable(_BACKEND_ERROR) from exc


def _decode_canonical(value: object, expected_length: int) -> bytes | None:
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
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != expected_length or canonical != value:
        return None
    return decoded


class CryptographyEd25519RootIssuerSignatureVerifier:
    """Verify exact signatures with one already-resolved trusted public key."""

    def __init__(self, *, backend_loader: Callable[[], Tuple[Any, Any]] = _load_cryptography) -> None:
        self._backend_loader = backend_loader

    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool:
        if algorithm != ED25519_ALGORITHM:
            return False
        public_bytes = _decode_canonical(public_key, 32)
        signature_bytes = _decode_canonical(signature, 64)
        if public_bytes is None or signature_bytes is None or not isinstance(payload, bytes):
            return False
        invalid_signature, public_key_type = self._backend_loader()
        try:
            verifier = public_key_type.from_public_bytes(public_bytes)
            verifier.verify(signature_bytes, payload)
        except invalid_signature:
            return False
        except (TypeError, ValueError):
            return False
        except Exception as exc:
            raise Ed25519VerificationBackendUnavailable(_BACKEND_ERROR) from exc
        return True


__all__ = [
    "CryptographyEd25519RootIssuerSignatureVerifier",
    "Ed25519VerificationBackendUnavailable",
]
