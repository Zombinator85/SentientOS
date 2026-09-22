"""Purpose-scoped, read-only custody for one root-issuer Ed25519 seed.

The boundary retrieves an operator-provisioned secret for one immutable reference,
validates its binding, and exposes a read-only view only for a callback's lifetime.
It deliberately provides neither signing nor key-administration operations.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypeVar

from sentientos.causal_resource_principal_authentication import ED25519_ALGORITHM

_KEYRING_NAMESPACE = "sentientos.causal_resource_principal.root_issuer"
_BASE64URL = re.compile(rb"[A-Za-z0-9_-]+")
_T = TypeVar("_T")


class RootIssuerPrivateKeyCustodyError(RuntimeError):
    """A fixed, redacted failure at the private signing-key custody boundary."""


@dataclass(frozen=True)
class RootIssuerSigningKeyReference:
    """Immutable, non-secret operator binding for exactly one signing key."""

    issuer_id: str
    signing_key_id: str
    algorithm: str
    key_reference: str


class RootIssuerPrivateKeyBackend(Protocol):
    """Read the secret selected by one already-bound operator reference."""

    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray: ...


class OSKeyringRootIssuerPrivateKeyBackend:
    """Read-only production access to the dedicated root-issuer keyring namespace."""

    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        try:
            keyring = importlib.import_module("keyring")
            value = keyring.get_password(_KEYRING_NAMESPACE, reference.key_reference)
        except Exception as exc:
            raise RootIssuerPrivateKeyCustodyError(
                "signer_key_custody_backend_unavailable"
            ) from exc
        if value is None:
            raise RootIssuerPrivateKeyCustodyError("signer_key_custody_secret_missing")
        if not isinstance(value, str) or not value:
            raise RootIssuerPrivateKeyCustodyError("signer_key_custody_material_invalid")
        try:
            return bytearray(value, "ascii")
        except UnicodeEncodeError as exc:
            raise RootIssuerPrivateKeyCustodyError(
                "signer_key_custody_material_invalid"
            ) from exc


def _load_private_key_type() -> Any:
    try:
        module = importlib.import_module(
            "cryptography.hazmat.primitives.asymmetric.ed25519"
        )
        return module.Ed25519PrivateKey
    except (ImportError, AttributeError) as exc:
        raise RootIssuerPrivateKeyCustodyError(
            "signer_key_custody_backend_unavailable"
        ) from exc


def _decode_seed(encoded: bytearray) -> bytearray:
    if _BASE64URL.fullmatch(encoded) is None:
        raise RootIssuerPrivateKeyCustodyError("signer_key_custody_material_invalid")
    try:
        decoded = base64.b64decode(
            bytes(encoded) + b"=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, TypeError) as exc:
        raise RootIssuerPrivateKeyCustodyError(
            "signer_key_custody_material_invalid"
        ) from exc
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).rstrip(b"=") != encoded:
        raise RootIssuerPrivateKeyCustodyError("signer_key_custody_material_invalid")
    return bytearray(decoded)


class RootIssuerPrivateKeyCustody:
    """Bounded use of one configured seed; no material is retained between calls."""

    def __init__(
        self,
        *,
        reference: RootIssuerSigningKeyReference,
        backend: RootIssuerPrivateKeyBackend,
        private_key_type_loader: Callable[[], Any] = _load_private_key_type,
    ) -> None:
        self._reference = reference
        self._backend = backend
        self._private_key_type_loader = private_key_type_loader

    def use_signing_material(
        self,
        *,
        issuer_id: str,
        signing_key_id: str,
        algorithm: str,
        consumer: Callable[[memoryview], _T],
    ) -> _T:
        expected = self._reference
        if algorithm != ED25519_ALGORITHM or (
            issuer_id,
            signing_key_id,
            algorithm,
        ) != (expected.issuer_id, expected.signing_key_id, expected.algorithm):
            raise RootIssuerPrivateKeyCustodyError(
                "signer_key_custody_binding_mismatch"
            )
        encoded: bytearray | None = None
        seed: bytearray | None = None
        try:
            try:
                encoded = self._backend.read_configured(expected)
            except RootIssuerPrivateKeyCustodyError:
                raise
            except Exception as exc:
                raise RootIssuerPrivateKeyCustodyError(
                    "signer_key_custody_backend_unavailable"
                ) from exc
            if not isinstance(encoded, bytearray):
                raise RootIssuerPrivateKeyCustodyError(
                    "signer_key_custody_material_invalid"
                )
            seed = _decode_seed(encoded)
            try:
                private_key = self._private_key_type_loader().from_private_bytes(bytes(seed))
                public_raw = private_key.public_key().public_bytes_raw()
            except RootIssuerPrivateKeyCustodyError:
                raise
            except Exception as exc:
                raise RootIssuerPrivateKeyCustodyError(
                    "signer_key_custody_material_invalid"
                ) from exc
            derived_key_id = "ed25519-sha256:" + hashlib.sha256(public_raw).hexdigest()
            if derived_key_id != expected.signing_key_id:
                raise RootIssuerPrivateKeyCustodyError(
                    "signer_key_custody_key_id_mismatch"
                )
            return consumer(memoryview(seed).toreadonly())
        finally:
            if seed is not None:
                seed[:] = b"\x00" * len(seed)
            if encoded is not None:
                encoded[:] = b"\x00" * len(encoded)


__all__ = [
    "OSKeyringRootIssuerPrivateKeyBackend",
    "RootIssuerPrivateKeyBackend",
    "RootIssuerPrivateKeyCustody",
    "RootIssuerPrivateKeyCustodyError",
    "RootIssuerSigningKeyReference",
]
